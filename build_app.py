import PyInstaller.__main__
import os

# 当前目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 应用图标(如果有)
icon_path = os.path.join(current_dir, 'app_icon.ico')  # 请确保此文件存在，或删除相关参数

# PyInstaller参数
params = [
    'OpenHandsStarterV2.py',    # 您的主脚本
    '--name=OpenHands部署助手',  # 输出的exe名称
    '--onefile',                # 生成单文件
    '--windowed',               # 使用GUI，不显示控制台窗口
    '--add-data=app_icon.ico;.', # 添加数据文件，格式为"源文件;目标目录"
    f'--icon={icon_path}',      # 应用图标
    '--clean',                  # 清理临时文件
    '--noconfirm',              # 覆盖输出目录
]

# 运行PyInstaller
PyInstaller.__main__.run(params)
