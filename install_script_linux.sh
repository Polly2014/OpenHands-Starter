#!/bin/bash
# filepath: install_openhands.sh

# 打印彩色标题
print_title() {
  echo -e "\e[1;36m==================================================\e[0m"
  echo -e "\e[1;36m $1 \e[0m"
  echo -e "\e[1;36m==================================================\e[0m"
}

# 检查脚本是否以root运行
if [ "$(id -u)" -eq 0 ]; then
  echo "警告: 不建议以root用户运行此脚本。请使用普通用户并配合sudo权限。"
  read -p "是否继续? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
fi

# 1. 安装Docker
print_title "1. 安装Docker"
sudo apt update
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io

# 2. 安装Docker Compose
print_title "2. 安装Docker Compose"
DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep -oP '"tag_name": "\K[^"]+')
echo "安装Docker Compose版本: $DOCKER_COMPOSE_VERSION"
sudo curl -L "https://github.com/docker/compose/releases/download/$DOCKER_COMPOSE_VERSION/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 3. 将当前用户添加到docker组
print_title "3. 配置Docker权限"
sudo usermod -aG docker $USER
echo "已将当前用户添加到docker组，这可能需要重新登录才能生效"

# 即时生效权限的几种方法
print_title "3.1 使Docker权限即时生效"
echo "使用newgrp命令获取新的docker组权限"
if [ -z "$SUDO_USER" ]; then
  # 直接以普通用户运行脚本的情况
  exec sg docker -c "bash -c \"
  echo '✅ 已成功切换到docker组环境';
  docker --version;
  \""
else
  # 通过sudo运行脚本的情况
  echo "脚本通过sudo运行，请在脚本完成后重新登录或执行 'newgrp docker' 以应用权限"
fi

# 4. 验证安装
print_title "4. 验证Docker安装"
docker --version || echo "Docker安装可能有问题，请退出并重新登录后再验证"
docker-compose --version || echo "Docker Compose安装可能有问题"

# 5. 创建工作目录和配置文件
print_title "5. 设置OpenHands环境"

# 创建工作目录
HOME_DIR=$HOME
WORKSPACE_DIR="$HOME_DIR/AICoder_Workspace"
mkdir -p "$WORKSPACE_DIR"
echo "工作目录已创建: $WORKSPACE_DIR"

# 创建docker-compose.yaml
cat > "$HOME_DIR/docker-compose.yaml" << EOL
services:
  openhands-app:
    image: docker.all-hands.dev/all-hands-ai/openhands:latest
    container_name: openhands-app
    environment:
      SANDBOX_RUNTIME_CONTAINER_IMAGE: docker.all-hands.dev/all-hands-ai/runtime:0.27-nikolaik
      LOG_ALL_EVENTS: "true"
      SANDBOX_USER_ID: "polly"
      WORKSPACE_MOUNT_PATH: /home/openhands/workspace
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ~/.openhands-state:/.openhands-state
      - $WORKSPACE_DIR:/home/openhands/workspace
    ports:
      - "80:3000"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    tty: true
    stdin_open: true
    restart: unless-stopped
EOL

echo "docker-compose.yaml 已创建: $HOME_DIR/docker-compose.yaml"

# 6. 尝试启动Docker服务
print_title "6. 启动OpenHands服务"
cd "$HOME_DIR"

# 检查用户是否在docker组中
if groups $USER | grep -q '\bdocker\b'; then
  docker-compose up -d
  echo "OpenHands服务已启动"
else
  echo "当前会话中用户不在docker组，尝试使用新组权限启动服务"
  # 使用newgrp命令在当前会话中获取docker组权限
  echo "请在看到此消息后手动执行以下命令:"
  echo -e "\e[1;33mnewgrp docker\e[0m"
  echo -e "\e[1;33mcd $HOME_DIR && docker-compose up -d\e[0m"
fi

# 7. 展示使用信息
print_title "7. 使用说明"
echo "OpenHands服务启动成功后，可通过浏览器访问: http://localhost:80"
echo ""
echo "可用命令:"
echo "启动服务: cd $HOME_DIR && docker-compose up -d"
echo "停止服务: cd $HOME_DIR && docker-compose down"
echo "查看日志: cd $HOME_DIR && docker-compose logs -f"
echo "重启服务: cd $HOME_DIR && docker-compose restart"
echo ""
echo "工作目录: $WORKSPACE_DIR"
echo "该目录已挂载到OpenHands容器内部的/home/openhands/workspace"

print_title "安装完成"
echo "注意：如果出现权限问题，请尝试注销并重新登录，或重启系统"