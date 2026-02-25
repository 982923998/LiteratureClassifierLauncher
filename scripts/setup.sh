#!/bin/bash
# 快速开始脚本

echo "文献归类系统 - 快速开始"
echo "========================"
echo ""

# 检查 Python
echo "1. 检查 Python 环境..."
python3 --version

# 安装依赖
echo ""
echo "2. 安装依赖包..."
cd /Users/chenmayao/Desktop/code/文献归类
pip3 install -r requirements.txt

# 创建 .env 文件
echo ""
echo "3. 配置环境变量..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "已创建 .env 文件，请编辑并填入你的 GEMINI_API_KEY"
    echo ""
    echo "获取 API Key: https://aistudio.google.com/app/apikey"
    echo ""
    read -p "按回车键继续..."
else
    echo ".env 文件已存在"
fi

echo ""
echo "4. 准备就绪！"
echo ""
echo "使用方法："
echo "  - 测试单个文件: python3 src/main.py --limit 1"
echo "  - 批量处理:     python3 src/main.py"
echo ""
