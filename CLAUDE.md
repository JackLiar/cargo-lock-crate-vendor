# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

一个 Python CLI 工具，读取 Rust 的 `Cargo.lock` 文件，从 crates.io-index 解析 crate 元数据，从镜像站下载 `.crate` 文件（gzip 包）。支持下载指定版本、全部版本或最新 N 个版本。

## 构建与运行

- **包管理器**: `uv`（见 `uv.lock`）
- **安装依赖**: `uv sync`
- **运行工具**: `uv run cargo-lock-crate-vendor --help`

本项目没有测试。

## 架构

整个应用位于单个文件：`src/cargo_lock_crate_vendor/__main__.py`。基于 `asyncio` + `httpx` 的异步 CLI。

### 核心类型

- **`Crate`** — `(name, version)` 二元组，标识一个 Rust crate。
- **`Index`** — crate 的索引条目（name + content）；`dir()` 方法按 crates.io-index 的前缀分割规则，将 crate 名映射到子目录路径。

### 核心流程

1. **解析输入** — 支持 `Cargo.lock` 文件（TOML 格式，读取 `package` 表）或 `--name`/`--version` 指定单个 crate。跳过 workspace crate（无 `source` 字段）和 git 来源的 crate。
2. **收集索引** — 为每个 crate 从 crates.io-index 获取索引文件（从 GitHub raw 或 `--registry` 指定的本地克隆）。跳过 `--index-output` 中已存在的索引。
3. **扩展版本**（可选）— 若设置了 `--all` 或 `--max-previous`，读取索引的 JSON-lines 内容，发现更多版本。
4. **下载 crate** — 从 SJTU S3 镜像站下载 `.crate` 文件。通过魔术数字验证（`\x1f\x8b` = gzip），非 gzip 响应跳过并警告。
5. **保存到磁盘** — crate 保存到 `crates/<name>/<version>/download`；索引按 crates.io-index 目录结构保存。

### crates.io-index 目录规则

`get_directory()` 实现标准的 crates.io-index 路径方案：
- 1-2 字符的 crate 名 → `"1"` 或 `"2"`
- 3 字符 → `"3/<首字符>"`
- 4+ 字符 → `"<前两字符>/<随后两字符>"`

## CLI 选项

| 参数 | 说明 |
|---|---|
| `-i/--input` | `Cargo.lock` 文件路径 |
| `-n/--name` + `-v/--version` | 指定单个 crate |
| `--all` | 下载匹配 crate 的全部版本 |
| `--max-previous N` | 下载匹配 crate 的最新 N 个版本 |
| `-o/--output` | `.crate` 保存目录（默认：`crates/`） |
| `--index-output` | 索引保存目录（默认：`index/`） |
| `-r/--registry` | 本地 crates.io-index git 克隆路径（避免从 GitHub 拉取） |

## 注意事项

- 下载 URL 硬编码了 SJTU 的 crates.io 镜像，这是有意为之，不直接访问 crates.io。
- 已下载的 crate 和索引通过磁盘文件跟踪，支持增量/断点续传。
