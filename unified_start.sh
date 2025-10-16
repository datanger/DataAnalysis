#!/bin/bash
# 智能股票数据分析平台 - 统一启动脚本
# unified_start.sh

# 设置项目根目录
PROJECT_ROOT="/home/niejie/work/DataAnalysis"
STOCK_SYS_DIR="$PROJECT_ROOT/StockAnal_Sys"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查并清理端口
check_and_clean_port() {
    local port=8888
    log_info "检查端口 $port 是否被占用..."
    
    # 检查端口是否被占用
    if lsof -i :$port >/dev/null 2>&1; then
        log_warning "端口 $port 被占用，正在清理..."
        
        # 获取占用端口的进程ID
        local pids=$(lsof -ti :$port)
        
        if [ -n "$pids" ]; then
            log_info "发现占用端口的进程: $pids"
            
            # 尝试优雅地终止进程
            for pid in $pids; do
                if kill -TERM $pid 2>/dev/null; then
                    log_info "正在终止进程 $pid..."
                    sleep 2
                    
                    # 检查进程是否还在运行
                    if kill -0 $pid 2>/dev/null; then
                        log_warning "进程 $pid 未响应TERM信号，强制终止..."
                        kill -KILL $pid 2>/dev/null
                    fi
                fi
            done
            
            # 等待端口释放
            sleep 3
            
            # 再次检查端口是否已释放
            if lsof -i :$port >/dev/null 2>&1; then
                log_error "无法释放端口 $port，请手动检查"
                exit 1
            else
                log_success "端口 $port 已成功释放"
            fi
        else
            log_warning "无法获取占用端口的进程ID"
        fi
    else
        log_success "端口 $port 可用"
    fi
}

# 检查环境
check_environment() {
    log_info "检查项目环境..."
    
    # 检查项目目录
    if [ ! -d "$PROJECT_ROOT" ]; then
        log_error "项目根目录不存在: $PROJECT_ROOT"
        exit 1
    fi
    
    # 检查统一依赖文件
    if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
        log_error "统一依赖文件不存在: $PROJECT_ROOT/requirements.txt"
        exit 1
    fi
    
    # 检查StockAnal_Sys
    if [ ! -d "$STOCK_SYS_DIR" ]; then
        log_error "StockAnal_Sys目录不存在: $STOCK_SYS_DIR"
        exit 1
    fi
    
    log_success "环境检查完成"
}

# 安装依赖
install_dependencies() {
    log_info "安装/更新依赖..."
    
    # 激活conda环境
    eval "$(conda shell.bash hook)"
    conda activate pandasai
    
    # 安装统一依赖
    pip install -r "$PROJECT_ROOT/requirements.txt"
    
    log_success "依赖安装完成"
}

# 启动增强版服务器
start_enhanced_server() {
    log_info "启动增强版智能股票分析系统..."
    
    # 检查并清理端口
    check_and_clean_port
    
    cd "$STOCK_SYS_DIR"
    
    # 激活conda环境
    eval "$(conda shell.bash hook)"
    conda activate pandasai
    
    # 启动服务器
    echo "[SUCCESS] 正在启动增强版服务器..."
    python -m app.web.web_server &
}

# 显示帮助
show_help() {
    echo "智能股票数据分析平台 - 统一管理脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  start     启动增强版服务器"
    echo "  stop      停止服务器"
    echo "  restart   重启服务器"
    echo "  status    检查服务器状态"
    echo "  install   安装/更新依赖"
    echo "  check     检查环境"
    echo "  clean     清理端口8888"
    echo "  help      显示此帮助信息"
    echo ""
    echo "项目结构:"
    echo "  $PROJECT_ROOT/"
    echo "  ├── StockAnal_Sys/          # 股票分析系统"
    echo "  ├── DeepResearch/           # 深度研究AI"
    echo "  ├── OpenHands/              # AI开发代理"
    echo "  ├── pandas-ai/              # 自然语言数据分析"
    echo "  └── requirements.txt        # 统一依赖文件"
}

# 主函数
main() {
    case "${1:-start}" in
        "start")
            check_environment
            start_enhanced_server
            ;;
        "stop")
            cd "$STOCK_SYS_DIR"
            ./enhanced_start.sh stop
            ;;
        "restart")
            cd "$STOCK_SYS_DIR"
            ./enhanced_start.sh restart
            ;;
        "status")
            cd "$STOCK_SYS_DIR"
            ./enhanced_start.sh status
            ;;
        "install")
            check_environment
            install_dependencies
            ;;
        "check")
            check_environment
            ;;
        "clean")
            check_and_clean_port
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            log_error "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
