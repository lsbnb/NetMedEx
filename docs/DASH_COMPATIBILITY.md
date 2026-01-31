# Dash 版本相容性指南

## 問題描述

NetMedEx 使用 Dash 作為 Web 框架，但 Dash 在 2.x → 3.x 版本升級時有 **Breaking Changes**，導致相容性問題。

### 常見錯誤

```
ModuleNotFoundError: No module named 'dash.long_callback'
```

## 解決方案

### ✅ Dash 3.x 正確寫法 (當前使用)

```python
# webapp/app.py
import diskcache
from dash import Dash, DiskcacheManager  # ✅ 直接從 dash 導入

cache = diskcache.Cache("./cache")
background_callback_manager = DiskcacheManager(cache)  # ✅ 使用 DiskcacheManager

app = Dash(
    __name__,
    background_callback_manager=background_callback_manager,  # ✅ 參數名稱正確
)
```

### ❌ Dash 2.x 舊寫法 (已棄用)

```python
# 不要使用以下寫法！
from dash.long_callback import DiskcacheLongCallbackManager  # ❌ 模組已移除

long_callback_manager = DiskcacheLongCallbackManager(cache)  # ❌ 類名已更改

app = Dash(
    __name__,
    long_callback_manager=long_callback_manager,  # ❌ 參數名稱已更改
)
```

## API 變更對照表

| 項目 | Dash 2.x | Dash 3.x |
|------|---------|---------|
| **導入路徑** | `from dash.long_callback import ...` | `from dash import ...` |
| **Manager 類名** | `DiskcacheLongCallbackManager` | `DiskcacheManager` |
| **app 參數名** | `long_callback_manager` | `background_callback_manager` |
| **Decorator** | `@app.long_callback()` | `@app.callback(..., background=True)` |

## Python 版本要求

- **推薦**: Python >= 3.11
- **最低**: Python >= 3.9 (已測試可運行)
- **Dash 版本**: 3.x (當前測試: 3.4.0)

## 啟動應用程式

### 方法 1: 使用 CLI (推薦)
```bash
netmedex run
```

### 方法 2: 直接運行
```bash
python -m webapp.app
```

### 方法 3: 指定主機和端口
```bash
HOST=127.0.0.1 PORT=8050 python -m webapp.app
```

## 常見問題排除

### 1. 端口被占用
```bash
# 錯誤: Address already in use Port 8050 is in use
# 解決方案: 關閉占用端口的程序
lsof -ti:8050 | xargs kill -9

# 或使用不同端口
PORT=8051 python -m webapp.app
```

### 2. 主機名稱解析問題
```bash
# 錯誤: Temporary failure in name resolution
# 解決方案: 強制使用 localhost
HOST=127.0.0.1 python -m webapp.app
```

### 3. 模組導入錯誤
確保安裝了正確的依賴：
```bash
pip install -r requirements.txt
# 或
pip install netmedex
```

## 測試環境

已在以下環境測試通過：
- ✅ Python 3.9.18 + Dash 3.4.0
- ✅ Python 3.11+ + Dash 3.4.0
- ✅ Python 3.12+ + Dash 3.4.0

## 參考資料

- [Dash 3.0 Migration Guide](https://community.plotly.com/t/dash-3-0-0-release/80883)
- [Dash Background Callbacks](https://dash.plotly.com/background-callbacks)
- [DiskcacheManager API](https://dash.plotly.com/reference#diskcachemanager)
