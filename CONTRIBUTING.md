# Contributing to TraceViz

感谢你对 TraceViz 的贡献！

## 开发环境搭建

```bash
# 克隆仓库
git clone https://github.com/shixy96/traceviz.git
cd traceviz

# 安装依赖（需要 uv）
uv sync --extra dev

# 安装 pre-commit hooks
pre-commit install
```

## 代码规范

- 使用 [Ruff](https://docs.astral.sh/ruff/) 进行 lint 和格式化
- 行宽上限 120 字符
- 使用双引号字符串

```bash
# lint 检查
uv run ruff check traceviz/ tests/

# 格式化
uv run ruff format traceviz/ tests/
```

## 测试

所有 PR 必须通过测试：

```bash
uv run pytest --cov --cov-report=term-missing
```

## PR 流程

1. Fork 仓库并创建特性分支
2. 编写代码和测试
3. 确保 `ruff check` 和 `ruff format --check` 通过
4. 确保所有测试通过
5. 提交 PR，描述你的修改内容和动机
