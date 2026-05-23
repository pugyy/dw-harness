#!/usr/bin/env bash
# init.sh - 一键初始化 dw-harness 到你的数仓项目
# 用法: bash init.sh /path/to/your-dw-project

set -euo pipefail

TARGET="${1:-}"

if [ -z "$TARGET" ]; then
    echo "用法 / Usage: bash init.sh /path/to/your-dw-project"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/template/.claude"
TARGET_CLAUDE="$TARGET/.claude"

if [ ! -d "$SOURCE" ]; then
    echo "错误: 找不到模板目录 template/.claude"
    echo "Error: template directory not found at template/.claude"
    exit 1
fi

if [ ! -d "$TARGET" ]; then
    echo "目标目录不存在，是否创建? / Target directory does not exist. Create it? (y/n)"
    read -r answer
    if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
        mkdir -p "$TARGET"
    else
        exit 0
    fi
fi

if [ -d "$TARGET_CLAUDE" ]; then
    echo "警告: $TARGET_CLAUDE 已存在，是否覆盖? / Warning: $TARGET_CLAUDE already exists. Overwrite? (y/n)"
    read -r answer
    if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
        echo "已取消 / Aborted"
        exit 0
    fi
    rm -rf "$TARGET_CLAUDE"
fi

cp -r "$SOURCE" "$TARGET_CLAUDE"
echo ""
echo "========================================"
echo "  模板已复制到 / Template copied to:"
echo "  $TARGET_CLAUDE"
echo "========================================"
echo ""
echo "下一步 / Next steps:"
echo ""
echo "  1. 编辑 CLAUDE.md，填写你的项目信息 / Edit CLAUDE.md with your project info:"
echo "     $TARGET_CLAUDE/CLAUDE.md"
echo ""
echo "  2. 如果你的系统只有 python3，改一下 hooks 命令 / If you only have python3:"
echo "     sed -i 's/python /\.claude\/hooks\//  python3 .claude/hooks/' $TARGET_CLAUDE/settings.json"
echo ""
echo "  3. 启动 Claude Code / Start Claude Code:"
echo "     cd $TARGET && claude"
echo ""

if command -v ${EDITOR:-nano} &>/dev/null; then
    echo "是否现在编辑 CLAUDE.md? / Edit CLAUDE.md now? (y/n)"
    read -r answer
    if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
        ${EDITOR:-nano} "$TARGET_CLAUDE/CLAUDE.md"
    fi
fi
