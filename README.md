# 高频电商价格指数系统

基于ClickHouse的电商商品日度价格指数计算系统，支持拉氏、派氏、费雪三种指数计算，提供可视化趋势图和数据导出功能。

## 环境要求

- Python 3.10+
- ClickHouse 服务器（可访问）
- 阿里云OSS（存储原始数据）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
# ClickHouse
CK_HOST=your-clickhouse-host
CK_PORT=8123
CK_USER=default
CK_PASSWORD=your-password
CK_DATABASE=default

# 阿里云OSS
OSS_ACCESS_KEY_ID=your-access-key-id
OSS_ACCESS_KEY_SECRET=your-access-key-secret
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET_NAME=your-bucket-name
```

> 注意：`.env` 文件已在 `.gitignore` 中，不会被提交。

### 3. 一键运行完整流程

```bash
python -m src.main run-pipeline
```

该命令将自动完成：建表 → 从OSS导入数据 → 计算所有指数。

## 主要命令

所有命令通过 `python -m src.main <command>` 执行：

| 命令 | 说明 |
|------|------|
| `create-tables` | 创建ClickHouse数据表 |
| `import` | 导入所有数据（分类+商品+价格） |
| `compute` | 计算所有日期价格指数 |
| `compute-latest` | 仅计算最新日期指数 |
| `run-pipeline` | 一键执行导入+计算 |
| `plot-total` | 绘制总指数趋势图 |
| `plot-category --category-id <id>` | 绘制指定分类指数图 |
| `list-categories` | 列出所有可用分类 |
| `export --format csv/excel` | 导出指数数据 |
| `verify` | 验证数据行数与状态 |

### 常用示例

```bash
# 绘制总指数图（保存为图片，不弹窗）
python -m src.main plot-total --no-show

# 导出Excel格式数据
python -m src.main export --format excel

# 指定基期日期重新计算
python -m src.main compute --base-date 2025-05-17 --recompute
```

## 项目结构

```
├── src/
│   ├── ingestion/      # 数据读取与清洗
│   ├── storage/        # ClickHouse/OSS客户端封装
│   ├── compute/        # 价格指数计算
│   ├── visualization/  # 绘图与数据导出
│   └── main.py         # CLI入口
├── docs/
│   └── 设计报告.md      # 详细设计文档
├── output/             # 图表与导出文件（自动生成）
├── .env                # 配置文件（自行创建）
└── requirements.txt
```

## 输出说明

运行后所有结果保存在 `output/` 目录：
- `*.png` - 指数趋势图
- `*.csv` / `*.xlsx` - 导出的指数数据

详细架构设计请参见 [docs/设计报告.md](docs/设计报告.md)。
