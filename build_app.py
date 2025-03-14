import os
import sys
import shutil
from PyInstaller.__main__ import run

# 应用信息
APP_NAME = "OpenHands PC部署助手"
ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "polly.ico")
MAIN_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OpenHandsStarter.py")

# 确保图标文件存在
if not os.path.exists(ICON_PATH):
    print(f"错误: 找不到图标文件 {ICON_PATH}")
    sys.exit(1)

# 清理之前的构建
dist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
build_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build")
spec_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OpenHandsStarter.spec")

for path in [dist_dir, build_dir]:
    if os.path.exists(path):
        print(f"清理 {path}")
        shutil.rmtree(path)

if os.path.exists(spec_file):
    os.remove(spec_file)

print(f"开始打包 {APP_NAME} 为单文件可执行程序...")

# PyInstaller 参数 - 使用 --onefile 选项生成单一 EXE 文件
pyinstaller_args = [
    MAIN_SCRIPT,
    '--name=OpenHandsStarter',
    f'--icon={ICON_PATH}',
    '--onefile',  # 生成单一 EXE 文件
    '--windowed',  # 使用 GUI 模式，不显示控制台
    '--noconfirm',  # 不询问是否覆盖
    '--clean',  # 清理旧的构建文件
    '--add-data', f'{ICON_PATH};.',  # 将图标文件添加到打包中
    '--hidden-import=PyQt5',
    '--hidden-import=requests',
    '--hidden-import=pywin32',  # 如果使用了 win32com 组件
]

print("使用以下参数运行 PyInstaller:")
print(' '.join(pyinstaller_args))

# 运行 PyInstaller
run(pyinstaller_args)

# 检查是否成功
exe_path = os.path.join(dist_dir, "OpenHandsStarter.exe")
if os.path.exists(exe_path):
    print(f"打包成功！可执行文件位于: {exe_path}")
    
    # 创建一个简单的批处理文件以便快速启动应用
    bat_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "启动OpenHands部署助手.bat")
    with open(bat_path, "w") as f:
        f.write(f'start "" "{exe_path}"\n')
    
    print(f"批处理启动文件已创建: {bat_path}")
    print(f"\n您可以通过运行 {exe_path} 来启动应用")
    
    # 将可执行文件复制到更明确的名称
    final_exe_path = os.path.join(dist_dir, f"{APP_NAME}.exe")
    shutil.copy(exe_path, final_exe_path)
    print(f"已复制可执行文件为: {final_exe_path}")
else:
    print("打包失败，未找到生成的可执行文件。")
    sys.exit(1)

print("\n注意: 使用单文件模式打包会导致应用启动时间变长，因为需要先解压文件到临时目录。")