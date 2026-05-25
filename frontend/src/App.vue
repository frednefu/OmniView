<template>
  <router-view />
</template>

<script setup>
</script>

<style>
/* ═══════════════════════════════════════════
   全局设计 Token — OmniView Design System
   ═══════════════════════════════════════════ */
:root {
  /* 主色调 */
  --color-primary: #6366f1;
  --color-primary-light: #818cf8;
  --color-primary-dark: #4f46e5;
  --color-primary-bg: #eef2ff;

  /* 语义色 */
  --color-success: #10b981;
  --color-success-light: #34d399;
  --color-success-bg: #ecfdf5;
  --color-warning: #f59e0b;
  --color-warning-light: #fbbf24;
  --color-warning-bg: #fffbeb;
  --color-danger: #ef4444;
  --color-danger-light: #f87171;
  --color-danger-bg: #fef2f2;
  --color-info: #6366f1;

  /* 中性色 */
  --color-bg: #f5f6fa;
  --color-bg-card: #ffffff;
  --color-text: #1e293b;
  --color-text-secondary: #64748b;
  --color-text-muted: #94a3b8;
  --color-border: #e2e8f0;
  --color-border-light: #f1f5f9;

  /* 侧边栏 */
  --sidebar-bg: #0f172a;
  --sidebar-bg-hover: rgba(255,255,255,0.06);
  --sidebar-bg-active: rgba(99,102,241,0.15);
  --sidebar-text: #94a3b8;
  --sidebar-text-active: #e2e8f0;
  --sidebar-width: 232px;
  --sidebar-collapsed: 64px;

  /* 阴影 */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.06);
  --shadow-lg: 0 12px 32px rgba(0,0,0,0.08);
  --shadow-card: 0 1px 3px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.04);

  /* 圆角 */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;

  /* 间距 */
  --gap-xs: 8px;
  --gap-sm: 12px;
  --gap-md: 16px;
  --gap-lg: 24px;
  --gap-xl: 32px;

  /* 过渡 */
  --transition-fast: 0.15s ease;
  --transition-normal: 0.25s ease;
}

/* ═══════════════════════════════════════════
   全局基础样式
   ═══════════════════════════════════════════ */
body {
  margin: 0;
  font-family: 'Inter', 'Helvetica Neue', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: var(--color-bg);
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.6;
}

#app {
  height: 100vh;
}

/* ═══════════════════════════════════════════
   Element Plus 全局覆盖
   ═══════════════════════════════════════════ */

/* 主题色覆盖 */
:root {
  --el-color-primary: var(--color-primary);
  --el-color-primary-light-3: var(--color-primary-light);
  --el-color-primary-dark-2: var(--color-primary-dark);
  --el-color-success: var(--color-success);
  --el-color-warning: var(--color-warning);
  --el-color-danger: var(--color-danger);
}

/* 卡片 */
.el-card {
  border-radius: var(--radius-md) !important;
  border: 1px solid var(--color-border) !important;
  box-shadow: var(--shadow-card) !important;
  transition: box-shadow var(--transition-normal);
}
.el-card:hover {
  box-shadow: var(--shadow-md) !important;
}

/* 表格 */
.el-table {
  --el-table-border-color: var(--color-border-light);
  --el-table-header-bg-color: #f8fafc;
  --el-table-row-hover-bg-color: #f1f5f9;
  border-radius: var(--radius-md);
  overflow: hidden;
}
.el-table th.el-table__cell {
  background: #f8fafc;
  color: var(--color-text-secondary);
  font-weight: 600;
  font-size: 13px;
  border-bottom: 2px solid var(--color-border);
}
.el-table .el-table__row:hover > td {
  background: #f8fafc !important;
}

/* 按钮 */
.el-button--primary {
  --el-button-bg-color: var(--color-primary);
  --el-button-border-color: var(--color-primary);
  --el-button-hover-bg-color: var(--color-primary-light);
  --el-button-hover-border-color: var(--color-primary-light);
  border-radius: var(--radius-sm);
  font-weight: 500;
  transition: all var(--transition-fast);
}
.el-button {
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

/* 输入框 */
.el-input__wrapper {
  border-radius: var(--radius-sm) !important;
  box-shadow: none !important;
  border: 1px solid var(--color-border);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}
.el-input__wrapper:hover {
  border-color: var(--color-primary-light);
}
.el-input__wrapper.is-focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(99,102,241,0.1) !important;
}

/* 下拉菜单 */
.el-dropdown-menu {
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-lg);
  padding: 4px;
}

/* 标签 */
.el-tag {
  border-radius: 4px;
  font-weight: 500;
}

/* 对话框 */
.el-dialog {
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

/* 分页 */
.el-pagination {
  --el-pagination-button-bg-color: var(--color-bg-card);
}

/* 菜单（侧边栏内） */
.el-menu {
  border-right: none !important;
}
.el-menu-item {
  margin: 2px 8px;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}
.el-menu-item:hover {
  background: var(--sidebar-bg-hover) !important;
}
.el-menu-item.is-active {
  background: var(--sidebar-bg-active) !important;
  color: var(--sidebar-text-active) !important;
}

/* 空状态 */
.el-empty__description {
  color: var(--color-text-muted);
}

/* 日期选择器 */
.el-date-editor .el-range-input {
  font-size: 13px;
}

/* 页面过渡 */
.fade-page-enter-active,
.fade-page-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.fade-page-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.fade-page-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* 滚动条 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>
