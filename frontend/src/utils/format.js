/** 全局时间格式化 — 后端返回东八区时间，直接显示 */
export function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  return d.toLocaleString('zh-CN', { hour12: false })
}

export function formatDate(t) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return t
  return d.toLocaleDateString('zh-CN')
}
