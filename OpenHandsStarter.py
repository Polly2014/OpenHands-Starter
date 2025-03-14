import os
import sys
import platform
import subprocess
import json
import time
import webbrowser
import shutil
import tempfile
import threading
import requests
from pathlib import Path
from datetime import datetime

# PyQt导入
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QLabel, QProgressBar,
                            QMessageBox, QWizard, QWizardPage, QTextEdit, 
                            QLineEdit, QFileDialog, QCheckBox, QGroupBox,
                            QRadioButton, QTabWidget, QComboBox, QGridLayout,
                            QSpacerItem, QSizePolicy, QSystemTrayIcon, QMenu,
                            QAction, QStyle, QDialog, QTreeWidget, QTreeWidgetItem)
from PyQt5.QtGui import QIcon, QPixmap, QFont, QTextCursor, QColor
from PyQt5.QtCore import (Qt, QThread, pyqtSignal, QTimer, QUrl, QSize, 
                         QObject, pyqtSlot, QProcess, QSettings, QDir)


# 应用程序常量
APP_NAME = "OpenHands PC部署助手"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Polly"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".openhands-assistant")
LOG_FILE = os.path.join(CONFIG_DIR, "openhands-assistant.log")

# Docker配置模板
DOCKER_COMPOSE_TEMPLATE = '''
services:
  openhands-app:
    image: docker.all-hands.dev/all-hands-ai/openhands:0.27
    container_name: openhands-app
    environment:
      - SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:0.27-nikolaik
      - LOG_ALL_EVENTS=true
      - SANDBOX_USER_ID="1000"
      - WORKSPACE_MOUNT_PATH={workspace_path}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - {state_dir}:/.openhands-state
      - {workspace_dir}:/opt/workspace_base
    ports:
      - "{port}:3000"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    tty: true
    stdin_open: true
    restart: "no"
'''

# Docker Desktop下载URL
DOCKER_DESKTOP_DOWNLOAD_URL = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"

# 在文件顶部添加这个类
class SignalLabel(QLabel):
    textChanged = pyqtSignal(str)
    
    def setText(self, text):
        super().setText(text)
        self.textChanged.emit(text)

class AppConfig:
    """应用程序配置管理类"""
    
    def __init__(self):
        self.settings_file = os.path.join(CONFIG_DIR, "settings.json")
        self.default_settings = {
            "workspace_dir": os.path.join(os.path.expanduser("~"), "Docker_Workspace"),
            "state_dir": os.path.join(os.path.expanduser("~"), ".openhands-state"),
            "port": "80",
            "auto_start": False,
            "minimize_to_tray": True,
            "check_update": True,
            "last_check": "",
        }
        self.settings = self.load_settings()
        
    def load_settings(self):
        """加载应用设置"""
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
            
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载设置文件错误: {e}")
                return self.default_settings
        else:
            self.save_settings(self.default_settings)
            return self.default_settings
            
    def save_settings(self, settings=None):
        """保存应用设置"""
        if settings:
            self.settings = settings
            
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"保存设置文件错误: {e}")
            
    def get_setting(self, key, default=None):
        """获取指定设置项"""
        if default is None:
            return self.settings.get(key, self.default_settings.get(key))
        else:
            return self.settings.get(key, default)
        
    def update_setting(self, key, value):
        """更新指定设置项"""
        self.settings[key] = value
        self.save_settings()

class Logger:
    """日志记录类"""
    
    def __init__(self, log_file=LOG_FILE):
        self.log_file = log_file
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
    
    def log(self, message, level="INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"写入日志失败: {e}")
        
        if level in ["ERROR", "CRITICAL"]:
            print(log_entry)
    
    def info(self, message):
        """记录信息级别日志"""
        self.log(message, "INFO")
    
    def warning(self, message):
        """记录警告级别日志"""
        self.log(message, "WARNING")
    
    def error(self, message):
        """记录错误级别日志"""
        self.log(message, "ERROR")
    
    def critical(self, message):
        """记录严重级别日志"""
        self.log(message, "CRITICAL")

class SystemChecker:
    """系统检查和兼容性验证类"""
    
    def __init__(self, logger):
        self.logger = logger
        
    def is_windows_compatible(self):
        """检查是否为兼容的Windows版本"""
        if platform.system() != "Windows":
            self.logger.error("当前系统不是Windows系统")
            return False
            
        win_version = platform.win32_ver()[0]
        if float(win_version) < 10:
            self.logger.error(f"Windows版本 {win_version} 不满足Docker Desktop要求")
            return False
            
        return True
        
    def is_docker_installed(self):
        """检查Docker是否已安装"""
        try:
            result = subprocess.run(
                ["docker", "--version"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0:
                self.logger.info(f"Docker已安装: {result.stdout.strip()}")
                return True
            else:
                self.logger.info("Docker未安装或无法访问")
                return False
        except Exception as e:
            self.logger.warning(f"检查Docker安装失败: {e}")
            return False
            
    def is_docker_running(self):
        """检查Docker服务是否运行中"""
        try:
            result = subprocess.run(
                ["docker", "info"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0:
                self.logger.info("Docker服务运行正常")
                return True
            else:
                self.logger.warning("Docker服务未运行")
                return False
        except Exception as e:
            self.logger.warning(f"检查Docker服务状态失败: {e}")
            return False
            
    def check_virtualization(self):
        """检查虚拟化支持"""
        try:
            # 使用systeminfo检查Hyper-V要求
            result = subprocess.run(
                ["systeminfo"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            if "虚拟化已启用" in result.stdout or "Virtualization Support" in result.stdout:
                self.logger.info("虚拟化已启用")
                return True
            else:
                self.logger.warning("虚拟化可能未启用")
                return False
        except Exception as e:
            self.logger.warning(f"检查虚拟化支持失败: {e}")
            return False
            
    def check_wsl(self):
        """检查WSL状态"""
        try:
            result = subprocess.run(
                ["wsl", "--status"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0:
                self.logger.info("WSL已安装")
                return True
            else:
                self.logger.warning("WSL未安装或配置不正确")
                return False
        except Exception as e:
            self.logger.warning(f"检查WSL状态失败: {e}")
            return False
            
    def check_disk_space(self, min_space_gb=10):
        """检查可用磁盘空间"""
        try:
            # 检查C盘可用空间
            disk_usage = shutil.disk_usage("C:\\")
            free_space_gb = disk_usage.free / (1024 * 1024 * 1024)  # 转换为GB
            
            self.logger.info(f"C盘可用空间: {free_space_gb:.2f} GB")
            if free_space_gb < min_space_gb:
                self.logger.warning(f"C盘可用空间不足: {free_space_gb:.2f} GB, 建议至少 {min_space_gb} GB")
                return False
            return True
        except Exception as e:
            self.logger.warning(f"检查磁盘空间失败: {e}")
            return False

class DockerManager:
    """Docker管理类"""
    
    def __init__(self, logger):
        self.logger = logger
        
    def install_docker_desktop(self, progress_callback=None):
        """安装Docker Desktop"""
        self.logger.info("开始安装Docker Desktop")
        
        # 创建临时文件夹
        temp_dir = tempfile.mkdtemp()
        installer_path = os.path.join(temp_dir, "DockerDesktopInstaller.exe")
        
        try:
            # 下载安装程序
            if progress_callback:
                progress_callback("正在下载Docker Desktop安装程序...", 10)
                
            self.logger.info(f"从 {DOCKER_DESKTOP_DOWNLOAD_URL} 下载安装程序")
            
            response = requests.get(DOCKER_DESKTOP_DOWNLOAD_URL, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            
            with open(installer_path, 'wb') as f:
                if total_size == 0:
                    f.write(response.content)
                else:
                    downloaded = 0
                    for data in response.iter_content(chunk_size=4096):
                        downloaded += len(data)
                        f.write(data)
                        if progress_callback and total_size > 0:
                            percent = int(20 + (downloaded / total_size * 30))
                            progress_callback(f"正在下载Docker Desktop安装程序... {downloaded//(1024*1024)}MB/{total_size//(1024*1024)}MB", percent)
            
            # 执行安装程序
            if progress_callback:
                progress_callback("正在安装Docker Desktop...", 50)
                
            self.logger.info("开始安装Docker Desktop")
            
            # 使用管理员权限运行安装程序
            process = subprocess.Popen(
                ["powershell", "Start-Process", installer_path, "-ArgumentList 'install --quiet'", "-Verb", "RunAs", "-Wait"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                self.logger.info("Docker Desktop安装成功")
                if progress_callback:
                    progress_callback("Docker Desktop安装完成，等待启动服务...", 80)
                return True
            else:
                self.logger.error(f"Docker Desktop安装失败: {stderr.decode('utf-8')}")
                if progress_callback:
                    progress_callback(f"Docker Desktop安装失败: {stderr.decode('utf-8')}", 100)
                return False
                
        except Exception as e:
            self.logger.error(f"Docker Desktop安装过程中出错: {str(e)}")
            if progress_callback:
                progress_callback(f"安装出错: {str(e)}", 100)
            return False
        finally:
            # 清理临时文件
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    def generate_compose_file(self, config, target_path):
        """生成docker-compose.yaml文件"""
        try:
            workspace_path = config.get_setting("workspace_dir")
            workspace_dir = config.get_setting("workspace_dir")
            state_dir = config.get_setting("state_dir")
            port = config.get_setting("port")
            
            # 确保目录存在
            os.makedirs(workspace_dir, exist_ok=True)
            os.makedirs(state_dir, exist_ok=True)
            
            # 替换模板中的变量
            compose_content = DOCKER_COMPOSE_TEMPLATE.format(
                workspace_path="~/Docker_Workspace",  # 容器内的路径
                workspace_dir=workspace_dir.replace("\\", "/"),  # Host路径，转换为正斜杠
                state_dir=state_dir.replace("\\", "/"),
                port=port
            )
            
            # 写入文件
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(compose_content)
                
            self.logger.info(f"docker-compose.yaml已生成: {target_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"生成docker-compose.yaml失败: {str(e)}")
            return False
    
    def start_openhands(self, compose_file):
        """启动OpenHands容器"""
        try:
            self.logger.info(f"正在启动OpenHands，使用配置文件: {compose_file}")
            
            # 确认目录
            compose_dir = os.path.dirname(compose_file)
            
            # 执行docker-compose up
            process = subprocess.Popen(
                ["docker-compose", "-f", compose_file, "up", "-d"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=compose_dir
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                self.logger.info("OpenHands启动成功")
                return True, stdout
            else:
                self.logger.error(f"OpenHands启动失败: {stderr}")
                return False, stderr
                
        except Exception as e:
            self.logger.error(f"启动OpenHands过程中出错: {str(e)}")
            return False, str(e)
    
    def stop_openhands(self, compose_file):
        """停止OpenHands容器"""
        try:
            self.logger.info(f"正在停止OpenHands，使用配置文件: {compose_file}")
            
            # 确认目录
            compose_dir = os.path.dirname(compose_file)
            
            # 执行docker-compose down
            process = subprocess.Popen(
                ["docker-compose", "-f", compose_file, "down"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=compose_dir
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                self.logger.info("OpenHands已停止")
                return True, stdout
            else:
                self.logger.error(f"停止OpenHands失败: {stderr}")
                return False, stderr
                
        except Exception as e:
            self.logger.error(f"停止OpenHands过程中出错: {str(e)}")
            return False, str(e)
            
    def get_container_status(self):
        """获取OpenHands容器状态"""
        try:
            process = subprocess.Popen(
                ["docker", "ps", "-a", "--filter", "name=openhands-app", "--format", "{{.Status}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0 and stdout.strip():
                status = stdout.strip()
                self.logger.info(f"OpenHands容器状态: {status}")
                return True, status
            else:
                self.logger.info("OpenHands容器未运行")
                return False, "未运行"
                
        except Exception as e:
            self.logger.error(f"获取容器状态失败: {str(e)}")
            return False, f"错误: {str(e)}"
        
class SetupWizard(QWizard):
    """安装设置向导"""
    
    def __init__(self, config, logger, system_checker, docker_manager):
        super().__init__()
        
        self.config = config
        self.logger = logger
        self.system_checker = system_checker
        self.docker_manager = docker_manager
        
        self.setWindowTitle(f"{APP_NAME} 安装向导")
        self.setWizardStyle(QWizard.ModernStyle)
        
        # 设置页面大小
        self.setMinimumSize(700, 500)
        
        # 添加向导页面
        self.addPage(self.createIntroPage())
        self.addPage(self.createSystemCheckPage())
        self.addPage(self.createDockerInstallPage())
        self.addPage(self.createConfigPage())
        self.addPage(self.createCompletionPage())
        
    def createIntroPage(self):
        """创建向导介绍页"""
        page = QWizardPage()
        page.setTitle("欢迎使用OpenHands PC部署助手")
        
        # 页面布局
        layout = QVBoxLayout()
        
        # 添加logo
        logo_label = QLabel()
        # 如果有Logo图像，可以取消注释下面的代码并提供正确的路径
        '''
        # 使用同目录下的polly.ico作为logo
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "polly.ico")
        if os.path.exists(logo_path):
            # 从.ico文件加载图标并转换为QPixmap
            icon = QIcon(logo_path)
            logo_pixmap = icon.pixmap(200, 200)
            logo_label.setPixmap(logo_pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)
        else:
            # 如果找不到文件，记录警告信息
            print(f"警告：找不到logo文件: {logo_path}")
        '''
        
        # 介绍文字
        intro_text = """
        <h3>欢迎使用 OpenHands PC 部署助手！</h3>
        <p>本向导将帮助您完成以下设置：</p>
        <ul>
            <li>检查系统兼容性</li>
            <li>安装 Docker Desktop（如果需要）</li>
            <li>配置 OpenHands 运行环境</li>
            <li>部署并启动 OpenHands</li>
        </ul>
        <p>点击"下一步"开始安装流程。</p>
        """
        
        intro_label = QLabel(intro_text)
        intro_label.setWordWrap(True)
        intro_label.setTextFormat(Qt.RichText)
        
        layout.addWidget(intro_label)
        layout.addStretch(1)
        
        page.setLayout(layout)
        return page
    
    def createSystemCheckPage(self):
        """创建系统检查页"""
        page = QWizardPage()
        page.setTitle("系统兼容性检查")
        page.setSubTitle("检查您的系统是否满足运行OpenHands的要求")
        
        self.check_results = {}
        
        # 页面布局
        layout = QVBoxLayout()
        
        # 创建检查项目列表
        check_items_group = QGroupBox("系统检查项目")
        check_items_layout = QVBoxLayout()
        
        # 创建各检查项的标签和状态指示
        self.win_compat_label = QLabel("Windows版本检查: 等待检查...")
        self.virtualization_label = QLabel("虚拟化支持检查: 等待检查...")
        self.wsl_label = QLabel("WSL检查: 等待检查...")
        self.disk_space_label = QLabel("磁盘空间检查: 等待检查...")
        self.docker_install_label = QLabel("Docker安装检查: 等待检查...")
        self.docker_running_label = QLabel("Docker运行状态: 等待检查...")
        
        # 添加到布局
        check_items_layout.addWidget(self.win_compat_label)
        check_items_layout.addWidget(self.virtualization_label)
        check_items_layout.addWidget(self.wsl_label)
        check_items_layout.addWidget(self.disk_space_label)
        check_items_layout.addWidget(self.docker_install_label)
        check_items_layout.addWidget(self.docker_running_label)
        
        check_items_group.setLayout(check_items_layout)
        layout.addWidget(check_items_group)
        
        # 添加开始检查按钮
        self.start_check_button = QPushButton("开始系统检查")
        self.start_check_button.clicked.connect(self.perform_system_checks)
        layout.addWidget(self.start_check_button)
        
        # 检查结果摘要
        self.check_summary = SignalLabel("请点击上方按钮开始系统检查")
        self.check_summary.setWordWrap(True)
        layout.addWidget(self.check_summary)
        
        # 添加伸展区，使内容靠上显示
        layout.addStretch(1)
        
        page.setLayout(layout)
        
        # 注册字段，用于确定是否可以进入下一页
        # 修改这一行，将registerField方法调用移到page对象上
        page.registerField("system_check_passed*", self.check_summary, "text", self.check_summary.textChanged)
        
        return page
    
    def perform_system_checks(self):
        """执行系统检查"""
        self.start_check_button.setEnabled(False)
        self.check_summary.setText("正在检查系统...")
        
        # 使用QTimer延迟执行，以便UI可以更新
        QTimer.singleShot(100, self._run_system_checks)
    
    def _run_system_checks(self):
        """实际执行系统检查的方法"""
        all_passed = True
        
        # Windows版本检查
        win_compat = self.system_checker.is_windows_compatible()
        self.win_compat_label.setText(f"Windows版本检查: {'通过' if win_compat else '不兼容'}")
        self.check_results["win_compat"] = win_compat
        all_passed = all_passed and win_compat
        
        # 虚拟化支持检查
        virtualization = self.system_checker.check_virtualization()
        self.virtualization_label.setText(f"虚拟化支持检查: {'通过' if virtualization else '未启用'}")
        self.check_results["virtualization"] = virtualization
        all_passed = all_passed and virtualization
        
        # WSL检查
        wsl = self.system_checker.check_wsl()
        self.wsl_label.setText(f"WSL检查: {'通过' if wsl else '未安装或未启用'}")
        self.check_results["wsl"] = wsl
        # WSL问题不是严重错误，可以继续
        
        # 磁盘空间检查
        disk_space = self.system_checker.check_disk_space()
        self.disk_space_label.setText(f"磁盘空间检查: {'通过' if disk_space else '空间不足'}")
        self.check_results["disk_space"] = disk_space
        all_passed = all_passed and disk_space
        
        # Docker安装检查
        docker_installed = self.system_checker.is_docker_installed()
        self.docker_install_label.setText(f"Docker安装检查: {'已安装' if docker_installed else '未安装'}")
        self.check_results["docker_installed"] = docker_installed
        # Docker未安装不是错误，会在后续步骤安装
        
        # Docker运行状态检查
        if docker_installed:
            docker_running = self.system_checker.is_docker_running()
            self.docker_running_label.setText(f"Docker运行状态: {'运行中' if docker_running else '未运行'}")
            self.check_results["docker_running"] = docker_running
        else:
            self.docker_running_label.setText("Docker运行状态: 未安装Docker")
            self.check_results["docker_running"] = False
        
        # 更新总结信息
        if all_passed:
            if not docker_installed:
                self.check_summary.setText("系统检查完成：系统兼容，但需要安装Docker Desktop")
            elif not self.check_results.get("docker_running", False):
                self.check_summary.setText("系统检查完成：系统兼容，但Docker服务未运行，请启动Docker Desktop")
            else:
                self.check_summary.setText("系统检查完成：所有检查通过")
        else:
            error_items = []
            if not win_compat:
                error_items.append("- Windows版本不兼容")
            if not virtualization:
                error_items.append("- 未启用虚拟化")
            if not disk_space:
                error_items.append("- 磁盘空间不足")
            
            self.check_summary.setText(f"系统检查完成：存在以下问题\n{''.join(error_items)}")
        
        self.start_check_button.setEnabled(True)
    
    def createDockerInstallPage(self):
        """创建Docker安装页"""
        page = QWizardPage()
        page.setTitle("Docker安装")
        page.setSubTitle("安装或配置Docker Desktop")
        
        # 页面布局
        layout = QVBoxLayout()
        
        # Docker状态组
        docker_status_group = QGroupBox("Docker状态")
        docker_status_layout = QVBoxLayout()
        
        self.docker_status_label = SignalLabel("正在检查Docker状态...")
        docker_status_layout.addWidget(self.docker_status_label)
        
        docker_status_group.setLayout(docker_status_layout)
        layout.addWidget(docker_status_group)
        
        # Docker安装组
        docker_install_group = QGroupBox("Docker安装")
        docker_install_layout = QVBoxLayout()
        
        self.docker_install_button = QPushButton("安装Docker Desktop")
        self.docker_install_button.clicked.connect(self.install_docker)
        docker_install_layout.addWidget(self.docker_install_button)
        
        # 安装进度
        self.docker_install_progress = QProgressBar()
        self.docker_install_progress.setRange(0, 100)
        self.docker_install_progress.setValue(0)
        docker_install_layout.addWidget(self.docker_install_progress)
        
        # 安装状态
        self.docker_install_status = QLabel("点击上方按钮安装Docker Desktop")
        docker_install_layout.addWidget(self.docker_install_status)
        
        docker_install_group.setLayout(docker_install_layout)
        layout.addWidget(docker_install_group)
        
        # 添加伸展区
        layout.addStretch(1)
        
        page.setLayout(layout)
        
        # 初始化处理
        page.initializePage = self.initDockerInstallPage
        
        # 注册完成字段
        page.registerField("docker_install_completed*", self.docker_status_label, "text", self.docker_status_label.textChanged)
        
        return page
    
    def initDockerInstallPage(self):
        """初始化Docker安装页面"""
        docker_installed = self.system_checker.is_docker_installed()
        docker_running = self.system_checker.is_docker_running() if docker_installed else False
        
        if docker_installed and docker_running:
            self.docker_status_label.setText("Docker Desktop已安装且正在运行")
            self.docker_install_button.setEnabled(False)
            self.docker_install_status.setText("无需安装Docker Desktop")
        elif docker_installed and not docker_running:
            self.docker_status_label.setText("Docker Desktop已安装但未运行，请手动启动Docker Desktop")
            self.docker_install_button.setEnabled(False)
            self.docker_install_status.setText("请启动Docker Desktop后继续")
        else:
            self.docker_status_label.setText("未检测到Docker Desktop")
            self.docker_install_button.setEnabled(True)
            self.docker_install_status.setText("需要安装Docker Desktop")
    
    def install_docker(self):
        """安装Docker Desktop"""
        self.docker_install_button.setEnabled(False)
        self.docker_install_status.setText("正在准备安装Docker Desktop...")
        self.docker_install_progress.setValue(5)
        
        # 创建安装线程
        self.install_thread = DockerInstallThread(self.docker_manager)
        self.install_thread.progress_signal.connect(self.update_docker_install_progress)
        self.install_thread.finished.connect(self.docker_install_finished)
        self.install_thread.start()
    
    def update_docker_install_progress(self, message, value):
        """更新Docker安装进度"""
        self.docker_install_status.setText(message)
        self.docker_install_progress.setValue(value)
    
    def docker_install_finished(self, success):
        """Docker安装完成处理"""
        if success:
            self.docker_install_status.setText("Docker Desktop安装成功，请确保Docker服务已启动")
            self.docker_status_label.setText("Docker Desktop已安装")
            QMessageBox.information(self, "安装成功", 
                                   "Docker Desktop已成功安装。请确保Docker已启动，然后继续安装向导。")
        else:
            self.docker_install_status.setText("Docker Desktop安装失败，请手动安装")
            QMessageBox.warning(self, "安装失败", 
                              "Docker Desktop安装失败。请手动安装Docker Desktop，然后继续安装向导。")
        
        # 重新检测Docker状态
        self.initDockerInstallPage()
        self.docker_install_button.setEnabled(True)
    
    def createConfigPage(self):
        """创建OpenHands配置页面"""
        page = QWizardPage()
        page.setTitle("OpenHands配置")
        page.setSubTitle("配置OpenHands运行环境")
        
        # 页面布局
        layout = QVBoxLayout()
        
        # 工作空间配置组
        workspace_group = QGroupBox("工作空间配置")
        workspace_layout = QGridLayout()
        
        # 工作目录
        workspace_layout.addWidget(QLabel("工作目录:"), 0, 0)
        self.workspace_dir_edit = QLineEdit(self.config.get_setting("workspace_dir"))
        workspace_layout.addWidget(self.workspace_dir_edit, 0, 1)
        browse_workspace_button = QPushButton("浏览...")
        browse_workspace_button.clicked.connect(lambda: self.browse_directory(self.workspace_dir_edit))
        workspace_layout.addWidget(browse_workspace_button, 0, 2)
        
        # 状态目录
        workspace_layout.addWidget(QLabel("状态目录:"), 1, 0)
        self.state_dir_edit = QLineEdit(self.config.get_setting("state_dir"))
        workspace_layout.addWidget(self.state_dir_edit, 1, 1)
        browse_state_button = QPushButton("浏览...")
        browse_state_button.clicked.connect(lambda: self.browse_directory(self.state_dir_edit))
        workspace_layout.addWidget(browse_state_button, 1, 2)
        
        workspace_group.setLayout(workspace_layout)
        layout.addWidget(workspace_group)
        
        # 网络配置组
        network_group = QGroupBox("网络配置")
        network_layout = QGridLayout()
        
        # 端口配置
        network_layout.addWidget(QLabel("Web端口:"), 0, 0)
        self.port_edit = QLineEdit(self.config.get_setting("port"))
        network_layout.addWidget(self.port_edit, 0, 1)
        
        network_group.setLayout(network_layout)
        layout.addWidget(network_group)
        
        # 其他选项组
        options_group = QGroupBox("其他选项")
        options_layout = QVBoxLayout()
        
        # 自动启动选项
        self.auto_start_check = QCheckBox("系统启动时自动运行OpenHands")
        self.auto_start_check.setChecked(self.config.get_setting("auto_start"))
        options_layout.addWidget(self.auto_start_check)
        
        # 最小化到托盘选项
        self.minimize_to_tray_check = QCheckBox("关闭窗口时最小化到系统托盘")
        self.minimize_to_tray_check.setChecked(self.config.get_setting("minimize_to_tray"))
        options_layout.addWidget(self.minimize_to_tray_check)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # 添加伸展区
        layout.addStretch(1)
        
        page.setLayout(layout)
        
        # 注册字段，用于验证
        page.registerField("workspace_dir*", self.workspace_dir_edit)
        page.registerField("state_dir*", self.state_dir_edit)
        page.registerField("port*", self.port_edit)
        
        # 页面验证处理
        page.validatePage = self.validateConfigPage

        self.workspace_dir_edit.textChanged.connect(self.updateNextButtonState)
        self.state_dir_edit.textChanged.connect(self.updateNextButtonState)
        self.port_edit.textChanged.connect(self.updateNextButtonState)
        
        return page

    def updateNextButtonState(self):
        """Update Next button state based on field validation"""
        # Check if fields are valid and enable/disable Next button accordingly
        workspace_dir = self.workspace_dir_edit.text()
        state_dir = self.state_dir_edit.text()
        port = self.port_edit.text()
        
        # Basic validation
        is_valid = bool(workspace_dir.strip() and state_dir.strip() and port.strip())
        
        # Additional port validation
        if is_valid and port.strip():
            try:
                port_num = int(port)
                is_valid = 1 <= port_num <= 65535
            except ValueError:
                is_valid = False
        
        # Update button state
        self.button(QWizard.NextButton).setEnabled(is_valid)

    def browse_directory(self, line_edit):
        """浏览并选择目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择目录", line_edit.text())
        if directory:
            line_edit.setText(directory)

    def validateConfigPage(self):
        """验证配置页面内容并保存设置"""
        # 获取配置值
        workspace_dir = self.workspace_dir_edit.text()
        state_dir = self.state_dir_edit.text()
        port = self.port_edit.text()
        auto_start = self.auto_start_check.isChecked()
        minimize_to_tray = self.minimize_to_tray_check.isChecked()
        
        # 验证端口
        try:
            port_num = int(port)
            if port_num < 1 or port_num > 65535:
                QMessageBox.warning(self, "验证失败", "端口号必须在1-65535范围内")
                return False
        except ValueError:
            QMessageBox.warning(self, "验证失败", "端口号必须是有效数字")
            return False
        
        # 保存设置
        self.config.update_setting("workspace_dir", workspace_dir)
        self.config.update_setting("state_dir", state_dir)
        self.config.update_setting("port", port)
        self.config.update_setting("auto_start", auto_start)
        self.config.update_setting("minimize_to_tray", minimize_to_tray)
        
        # 确保目录存在
        try:
            os.makedirs(workspace_dir, exist_ok=True)
            os.makedirs(state_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "目录创建失败", f"无法创建目录: {str(e)}")
            return False
        
        return True
    
    def createCompletionPage(self):
        """创建完成页"""
        page = QWizardPage()
        page.setTitle("安装完成")
        page.setSubTitle("OpenHands设置已完成")
        
        # 页面布局
        layout = QVBoxLayout()
        
        # 完成消息
        completion_text = """
        <h3>恭喜！OpenHands设置已完成。</h3>
        <p>您已经成功完成了OpenHands的安装配置。接下来您可以：</p>
        <ul>
            <li>启动OpenHands服务</li>
            <li>使用Web浏览器访问OpenHands界面</li>
            <li>通过系统托盘图标管理OpenHands</li>
        </ul>
        <p>点击"完成"按钮关闭向导并启动OpenHands管理器。</p>
        """
        
        completion_label = QLabel(completion_text)
        completion_label.setWordWrap(True)
        completion_label.setTextFormat(Qt.RichText)
        
        layout.addWidget(completion_label)
        
        # 自动启动选项
        self.launch_on_exit_check = QCheckBox("完成后立即启动OpenHands")
        self.launch_on_exit_check.setChecked(True)
        layout.addWidget(self.launch_on_exit_check)
        
        # 添加伸展区
        layout.addStretch(1)
        
        page.setLayout(layout)
        
        # 页面完成处理
        page.validatePage = self.completeSetup
        
        return page
    
    def completeSetup(self):
        """完成安装向导"""
        # 生成docker-compose文件
        compose_dir = os.path.join(CONFIG_DIR, "compose")
        os.makedirs(compose_dir, exist_ok=True)
        compose_file = os.path.join(compose_dir, "docker-compose.yaml")
        
        success = self.docker_manager.generate_compose_file(self.config, compose_file)
        if not success:
            QMessageBox.warning(self, "配置文件生成失败", "无法生成docker-compose配置文件，请检查设置")
            return False
        
        # 保存compose文件路径到设置
        self.config.update_setting("compose_file", compose_file)
        
        # 标记安装向导已完成
        self.config.update_setting("setup_completed", True)
        self.config.update_setting("setup_date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # 是否自动启动
        self.config.update_setting("launch_on_exit", self.launch_on_exit_check.isChecked())
        
        return True
        
class DockerInstallThread(QThread):
    """Docker安装线程"""
    
    progress_signal = pyqtSignal(str, int)  # 用于更新安装进度的信号
    finished = pyqtSignal(bool)  # 安装完成信号，带成功/失败状态
    
    def __init__(self, docker_manager):
        super().__init__()
        self.docker_manager = docker_manager
        
    def run(self):
        """执行Docker安装"""
        success = self.docker_manager.install_docker_desktop(self.update_progress)
        self.finished.emit(success)
        
    def update_progress(self, message, value):
        """更新进度信息"""
        self.progress_signal.emit(message, value)
        
class MainWindow(QMainWindow):
    """主窗口类"""
    
    def __init__(self, config, logger, system_checker, docker_manager):
        super().__init__()
        
        self.config = config
        self.logger = logger
        self.system_checker = system_checker
        self.docker_manager = docker_manager
        
        # 应用程序状态
        self.is_service_running = False
        self.compose_file = self.config.get_setting("compose_file", "")
        
        # 设置窗口
        self.setup_ui()
        
        # 初始化系统托盘
        self.setup_tray()
        
        # 自动检查服务状态
        self.check_service_status()
        
        # 状态刷新计时器
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.check_service_status)
        self.status_timer.start(10000)  # 每10秒更新一次状态
        
    def setup_ui(self):
        """设置用户界面"""
        # 设置窗口基本属性
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(800, 600)

        # 设置窗口图标
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "polly.ico")
        if os.path.exists(logo_path):
            app_icon = QIcon(logo_path)
            self.setWindowIcon(app_icon)
        
        # 创建中央窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 添加标题标签
        title_label = QLabel(f"{APP_NAME}")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        main_layout.addWidget(title_label)
        
        # 状态指示区域
        status_group = QGroupBox("服务状态")
        status_layout = QHBoxLayout()
        
        self.status_icon_label = QLabel()
        status_layout.addWidget(self.status_icon_label)
        
        self.status_text_label = QLabel("正在检查服务状态...")
        status_layout.addWidget(self.status_text_label, 1)
        
        self.refresh_button = QPushButton("刷新状态")
        self.refresh_button.clicked.connect(self.check_service_status)
        status_layout.addWidget(self.refresh_button)
        
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)
        
        # 创建选项卡窗口
        tabs = QTabWidget()
        
        # 控制选项卡
        control_tab = QWidget()
        control_layout = QVBoxLayout(control_tab)
        
        # 服务控制按钮
        control_buttons_layout = QHBoxLayout()
        
        self.start_button = QPushButton("启动服务")
        self.start_button.clicked.connect(self.start_service)
        control_buttons_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("停止服务")
        self.stop_button.clicked.connect(self.stop_service)
        control_buttons_layout.addWidget(self.stop_button)
        
        self.restart_button = QPushButton("重启服务")
        self.restart_button.clicked.connect(self.restart_service)
        control_buttons_layout.addWidget(self.restart_button)
        
        control_layout.addLayout(control_buttons_layout)
        
        # 服务访问区域
        access_group = QGroupBox("访问OpenHands")
        access_layout = QVBoxLayout()
        
        access_info = QLabel(f"OpenHands Web界面将在以下地址可用：<br><b>http://localhost:{self.config.get_setting('port')}</b>")
        access_info.setTextFormat(Qt.RichText)
        access_layout.addWidget(access_info)
        
        open_browser_button = QPushButton("在浏览器中打开")
        open_browser_button.clicked.connect(self.open_in_browser)
        access_layout.addWidget(open_browser_button)
        
        access_group.setLayout(access_layout)
        control_layout.addWidget(access_group)
        
        # 日志输出区
        log_group = QGroupBox("服务日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        log_controls_layout = QHBoxLayout()
        
        self.auto_scroll_check = QCheckBox("自动滚动")
        self.auto_scroll_check.setChecked(True)
        log_controls_layout.addWidget(self.auto_scroll_check)
        
        clear_log_button = QPushButton("清除日志")
        clear_log_button.clicked.connect(self.log_text.clear)
        log_controls_layout.addWidget(clear_log_button)
        
        refresh_log_button = QPushButton("刷新日志")
        refresh_log_button.clicked.connect(self.refresh_logs)
        log_controls_layout.addWidget(refresh_log_button)
        
        log_layout.addLayout(log_controls_layout)
        
        log_group.setLayout(log_layout)
        control_layout.addWidget(log_group)
        
        tabs.addTab(control_tab, "控制台")
        
        # 设置选项卡
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        
        # 工作空间设置
        workspace_group = QGroupBox("工作空间设置")
        workspace_layout = QGridLayout()
        
        # 工作目录
        workspace_layout.addWidget(QLabel("工作目录:"), 0, 0)
        self.ws_dir_edit = QLineEdit(self.config.get_setting("workspace_dir"))
        workspace_layout.addWidget(self.ws_dir_edit, 0, 1)
        ws_browse_button = QPushButton("浏览...")
        ws_browse_button.clicked.connect(lambda: self.browse_directory(self.ws_dir_edit))
        workspace_layout.addWidget(ws_browse_button, 0, 2)
        
        # 状态目录
        workspace_layout.addWidget(QLabel("状态目录:"), 1, 0)
        self.ws_state_edit = QLineEdit(self.config.get_setting("state_dir"))
        workspace_layout.addWidget(self.ws_state_edit, 1, 1)
        state_browse_button = QPushButton("浏览...")
        state_browse_button.clicked.connect(lambda: self.browse_directory(self.ws_state_edit))
        workspace_layout.addWidget(state_browse_button, 1, 2)
        
        # 端口设置
        workspace_layout.addWidget(QLabel("Web端口:"), 2, 0)
        self.ws_port_edit = QLineEdit(self.config.get_setting("port"))
        workspace_layout.addWidget(self.ws_port_edit, 2, 1, 1, 2)
        
        workspace_group.setLayout(workspace_layout)
        settings_layout.addWidget(workspace_group)
        
        # 应用程序设置
        app_settings_group = QGroupBox("应用程序设置")
        app_settings_layout = QVBoxLayout()
        
        # 开机自启动选项
        self.auto_start_check = QCheckBox("开机时自动启动OpenHands部署助手")
        self.auto_start_check.setChecked(self.config.get_setting("auto_start"))
        app_settings_layout.addWidget(self.auto_start_check)
        
        # 最小化到托盘选项
        self.minimize_tray_check = QCheckBox("关闭窗口时最小化到系统托盘")
        self.minimize_tray_check.setChecked(self.config.get_setting("minimize_to_tray"))
        app_settings_layout.addWidget(self.minimize_tray_check)
        
        # 检查更新选项
        self.check_update_check = QCheckBox("启动时检查更新")
        self.check_update_check.setChecked(self.config.get_setting("check_update"))
        app_settings_layout.addWidget(self.check_update_check)
        
        app_settings_group.setLayout(app_settings_layout)
        settings_layout.addWidget(app_settings_group)
        
        # 保存设置按钮
        save_settings_button = QPushButton("保存设置")
        save_settings_button.clicked.connect(self.save_settings)
        settings_layout.addWidget(save_settings_button)
        
        # 添加伸展区
        settings_layout.addStretch(1)
        
        tabs.addTab(settings_tab, "设置")
        
        # 添加关于选项卡
        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)
        
        about_text = f"""
        <h2>{APP_NAME} v{APP_VERSION}</h2>
        <p>开发者：{APP_AUTHOR}</p>
        <p>这是一个用于Windows平台的OpenHands部署助手，可以帮助您快速设置OpenHands运行环境。</p>
        <p>特性：</p>
        <ul>
            <li>自动检查系统兼容性</li>
            <li>安装配置Docker环境</li>
            <li>管理OpenHands容器</li>
            <li>提供简单易用的Web界面接入</li>
        </ul>
        """
        
        about_label = QLabel(about_text)
        about_label.setWordWrap(True)
        about_label.setTextFormat(Qt.RichText)
        about_label.setAlignment(Qt.AlignCenter)
        about_layout.addWidget(about_label)
        
        check_update_button = QPushButton("检查更新")
        check_update_button.clicked.connect(self.check_for_updates)
        about_layout.addWidget(check_update_button)
        
        about_layout.addStretch(1)
        
        tabs.addTab(about_tab, "关于")
        
        # 将选项卡添加到主布局
        main_layout.addWidget(tabs)
    
    def setup_tray(self):
        """初始化系统托盘图标"""
        self.tray_icon = QSystemTrayIcon(self)
        
        # # 使用系统图标
        # self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        # 使用polly.ico作为托盘图标
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "polly.ico")
        if os.path.exists(logo_path):
            app_icon = QIcon(logo_path)
            self.tray_icon.setIcon(app_icon)
        else:
            # 如果找不到logo文件，使用系统默认图标
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        
        # 创建托盘菜单
        tray_menu = QMenu()
        
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        start_action = QAction("启动服务", self)
        start_action.triggered.connect(self.start_service)
        tray_menu.addAction(start_action)
        
        stop_action = QAction("停止服务", self)
        stop_action.triggered.connect(self.stop_service)
        tray_menu.addAction(stop_action)
        
        restart_action = QAction("重启服务", self)
        restart_action.triggered.connect(self.restart_service)
        tray_menu.addAction(restart_action)
        
        tray_menu.addSeparator()
        
        open_browser_action = QAction("在浏览器中打开", self)
        open_browser_action.triggered.connect(self.open_in_browser)
        tray_menu.addAction(open_browser_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        # 设置托盘菜单
        self.tray_icon.setContextMenu(tray_menu)
        
        # 托盘图标激活处理
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
        # 显示托盘图标
        if self.config.get_setting("minimize_to_tray"):
            self.tray_icon.show()
    
    def tray_icon_activated(self, reason):
        """托盘图标激活处理"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.activateWindow()
    
    def closeEvent(self, event):
        """窗口关闭事件处理"""
        if self.config.get_setting("minimize_to_tray") and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                APP_NAME,
                "应用已最小化到系统托盘，点击托盘图标可以恢复。",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            event.accept()
    
    def quit_application(self):
        """退出应用程序"""
        # 如果服务正在运行，提示用户
        if self.is_service_running:
            reply = QMessageBox.question(
                self, 
                "确认退出", 
                "OpenHands服务当前正在运行。退出应用程序将不会停止服务。\n\n确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                return
        
        QApplication.quit()
    
    def check_service_status(self):
        """检查OpenHands服务状态"""
        self.refresh_button.setEnabled(False)
        
        # 检查Docker是否运行
        if not self.system_checker.is_docker_running():
            self.status_text_label.setText("Docker服务未运行，请先启动Docker Desktop")
            # 设置红色图标
            self.status_icon_label.setText("⚠️")
            self.is_service_running = False
            self.update_control_buttons()
            self.refresh_button.setEnabled(True)
            return
        
        # 检查OpenHands容器状态
        is_running, status = self.docker_manager.get_container_status()
        self.is_service_running = is_running and "Up" in status
        
        if self.is_service_running:
            self.status_text_label.setText(f"OpenHands服务正在运行: {status}")
            self.status_icon_label.setText("✅")
        else:
            self.status_text_label.setText(f"OpenHands服务未运行: {status}")
            self.status_icon_label.setText("❌")
        
        self.update_control_buttons()
        self.refresh_logs()
        self.refresh_button.setEnabled(True)
    
    def update_control_buttons(self):
        """更新控制按钮状态"""
        docker_running = self.system_checker.is_docker_running()
        
        self.start_button.setEnabled(docker_running and not self.is_service_running)
        self.stop_button.setEnabled(self.is_service_running)
        self.restart_button.setEnabled(self.is_service_running)
    
    def start_service(self):
        """启动OpenHands服务"""
        if not self.compose_file or not os.path.exists(self.compose_file):
            QMessageBox.warning(self, "配置错误", "找不到docker-compose配置文件，请重新运行安装向导")
            return
        
        self.start_button.setEnabled(False)
        self.log_text.append("正在启动OpenHands服务...\n")
        
        # 启动服务
        success, output = self.docker_manager.start_openhands(self.compose_file)
        
        if success:
            self.log_text.append("OpenHands服务启动成功\n")
            QMessageBox.information(self, "启动成功", "OpenHands服务已成功启动")
        else:
            self.log_text.append(f"OpenHands服务启动失败:\n{output}\n")
            QMessageBox.critical(self, "启动失败", f"OpenHands服务启动失败，请查看日志了解详情")
        
        # 更新状态
        self.check_service_status()
    
    def stop_service(self):
        """停止OpenHands服务"""
        if not self.compose_file or not os.path.exists(self.compose_file):
            QMessageBox.warning(self, "配置错误", "找不到docker-compose配置文件，请重新运行安装向导")
            return
        
        reply = QMessageBox.question(
            self, 
            "确认停止", 
            "确定要停止OpenHands服务吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return
            
        self.stop_button.setEnabled(False)
        self.log_text.append("正在停止OpenHands服务...\n")
        
        # 停止服务
        success, output = self.docker_manager.stop_openhands(self.compose_file)
        
        if success:
            self.log_text.append("OpenHands服务已停止\n")
        else:
            self.log_text.append(f"停止OpenHands服务失败:\n{output}\n")
            QMessageBox.critical(self, "停止失败", f"停止OpenHands服务失败，请查看日志了解详情")
        
        # 更新状态
        self.check_service_status()
    
    def restart_service(self):
        """重启OpenHands服务"""
        if not self.compose_file or not os.path.exists(self.compose_file):
            QMessageBox.warning(self, "配置错误", "找不到docker-compose配置文件，请重新运行安装向导")
            return
        
        reply = QMessageBox.question(
            self, 
            "确认重启", 
            "确定要重启OpenHands服务吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return
            
        self.restart_button.setEnabled(False)
        self.log_text.append("正在重启OpenHands服务...\n")
        
        # 首先停止服务
        success, output = self.docker_manager.stop_openhands(self.compose_file)
        if not success:
            self.log_text.append(f"停止OpenHands服务失败:\n{output}\n")
            QMessageBox.critical(self, "重启失败", f"停止OpenHands服务失败，无法完成重启")
            self.check_service_status()
            return
            
        # 然后启动服务
        success, output = self.docker_manager.start_openhands(self.compose_file)
        if success:
            self.log_text.append("OpenHands服务重启成功\n")
        else:
            self.log_text.append(f"启动OpenHands服务失败:\n{output}\n")
            QMessageBox.critical(self, "重启失败", f"启动OpenHands服务失败，请查看日志了解详情")
        
        # 更新状态
        self.check_service_status()
    
    def open_in_browser(self):
        """在浏览器中打开OpenHands Web界面"""
        port = self.config.get_setting("port")
        url = f"http://localhost:{port}"
        
        try:
            webbrowser.open(url)
        except Exception as e:
            QMessageBox.warning(self, "打开浏览器失败", f"无法打开浏览器: {str(e)}")
    
    def refresh_logs(self):
        """刷新日志输出"""
        if not self.is_service_running:
            return
            
        try:
            # 获取容器日志 - FIX: Add utf-8 encoding
            process = subprocess.Popen(
                ["docker", "logs", "openhands-app", "--tail", "50"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',  # Add explicit UTF-8 encoding
                errors='replace'   # Replace characters that can't be decoded
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                combined_logs = stdout + stderr
                self.log_text.setText(combined_logs)
                
                if self.auto_scroll_check.isChecked():
                    # 滚动到底部
                    cursor = self.log_text.textCursor()
                    cursor.movePosition(QTextCursor.End)
                    self.log_text.setTextCursor(cursor)
        except Exception as e:
            self.log_text.append(f"获取日志失败: {str(e)}\n")
    
    def browse_directory(self, line_edit):
        """浏览并选择目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择目录", line_edit.text())
        if directory:
            line_edit.setText(directory)
    
    def save_settings(self):
        """保存设置"""
        # 获取UI中的设置值
        workspace_dir = self.ws_dir_edit.text()
        state_dir = self.ws_state_edit.text()
        port = self.ws_port_edit.text()
        auto_start = self.auto_start_check.isChecked()
        minimize_to_tray = self.minimize_tray_check.isChecked()
        check_update = self.check_update_check.isChecked()
        
        # 验证端口
        try:
            port_num = int(port)
            if port_num < 1 or port_num > 65535:
                QMessageBox.warning(self, "无效端口", "端口号必须在1-65535范围内")
                return
        except ValueError:
            QMessageBox.warning(self, "无效端口", "端口号必须是数字")
            return
        
        # 保存设置
        self.config.update_setting("workspace_dir", workspace_dir)
        self.config.update_setting("state_dir", state_dir)
        self.config.update_setting("port", port)
        self.config.update_setting("auto_start", auto_start)
        self.config.update_setting("minimize_to_tray", minimize_to_tray)
        self.config.update_setting("check_update", check_update)
        
        # 重新生成docker-compose文件
        compose_file = self.config.get_setting("compose_file")
        if compose_file:
            success = self.docker_manager.generate_compose_file(self.config, compose_file)
            if not success:
                QMessageBox.warning(self, "配置更新失败", "无法更新docker-compose配置文件")
                return
        
        # 设置开机自启
        if auto_start:
            self.setup_autostart(True)
        else:
            self.setup_autostart(False)
        
        # 更新托盘图标显示
        if minimize_to_tray:
            self.tray_icon.show()
        else:
            self.tray_icon.hide()
        
        QMessageBox.information(self, "设置已保存", "设置已成功保存。\n\n如果修改了端口或路径设置，需要重启OpenHands服务才能生效。")
    
    def setup_autostart(self, enable):
        """设置开机自启动"""
        # 对于Windows系统，创建或删除启动文件夹中的快捷方式
        try:
            import winreg
            import win32com.client
            
            # 获取当前可执行文件路径
            app_path = sys.executable
            
            # 获取启动文件夹路径
            startup_folder = os.path.join(
                os.environ["APPDATA"],
                "Microsoft\\Windows\\Start Menu\\Programs\\Startup"
            )
            
            shortcut_path = os.path.join(startup_folder, f"{APP_NAME}.lnk")
            
            if enable:
                # 创建快捷方式
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.TargetPath = app_path
                shortcut.WorkingDirectory = os.path.dirname(app_path)
                shortcut.Description = f"启动 {APP_NAME}"
                shortcut.Save()
                self.logger.info(f"已创建开机自启动快捷方式: {shortcut_path}")
            else:
                # 删除快捷方式
                if os.path.exists(shortcut_path):
                    os.remove(shortcut_path)
                    self.logger.info(f"已删除开机自启动快捷方式: {shortcut_path}")
                    
        except Exception as e:
            self.logger.error(f"设置开机自启动失败: {str(e)}")
    
    def check_for_updates(self):
        """检查更新"""
        # 这里只是一个示例，实际应用需要实现真正的更新检查逻辑
        QMessageBox.information(
            self, 
            "检查更新", 
            f"当前版本: {APP_VERSION}\n\n您使用的已是最新版本。"
        )
        
        # 更新最后检查时间
        self.config.update_setting("last_check", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
def main():
    """程序入口函数"""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出应用
    
    # 初始化配置
    config = AppConfig()
    
    # 初始化日志
    logger = Logger()
    logger.info(f"启动 {APP_NAME} v{APP_VERSION}")
    
    # 初始化系统检查器
    system_checker = SystemChecker(logger)
    
    # 初始化Docker管理器
    docker_manager = DockerManager(logger)
    
    # 检查设置完成状态，决定是否显示向导
    if not config.get_setting("setup_completed", False):
        # 显示设置向导
        wizard = SetupWizard(config, logger, system_checker, docker_manager)
        result = wizard.exec_()
        
        if result == QWizard.Rejected:
            logger.info("安装向导被取消，退出应用程序")
            return
            
        # 检查是否需要立即启动服务
        launch_on_exit = config.get_setting("launch_on_exit", False)
    else:
        launch_on_exit = False
    
    # 创建主窗口
    main_window = MainWindow(config, logger, system_checker, docker_manager)
    main_window.show()
    
    # 如果设置了启动时自动启动服务
    if launch_on_exit or config.get_setting("auto_start", False):
        # 使用QTimer以确保主窗口已完全初始化
        QTimer.singleShot(1000, main_window.start_service)
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
