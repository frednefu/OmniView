import api from './index'

// 备份任务
export function getBackupJobs(params) { return api.get('/backup/jobs', { params }).then(r => r.data) }
export function createBackupJob(data) { return api.post('/backup/jobs', data).then(r => r.data) }
export function getBackupJob(id) { return api.get(`/backup/jobs/${id}`).then(r => r.data) }
export function updateBackupJob(id, data) { return api.put(`/backup/jobs/${id}`, data).then(r => r.data) }
export function deleteBackupJob(id) { return api.delete(`/backup/jobs/${id}`).then(r => r.data) }
export function runBackupJob(id) { return api.post(`/backup/jobs/${id}/run`).then(r => r.data) }

// 备份历史
export function getBackupHistory(params) { return api.get('/backup/history', { params }).then(r => r.data) }
export function deleteBackupHistory(id) { return api.delete(`/backup/history/${id}`).then(r => r.data) }
export function verifyBackup(id) { return api.post(`/backup/history/${id}/verify`).then(r => r.data) }
export function getVerifyProgress(id) { return api.get(`/backup/history/${id}/verify-progress`).then(r => r.data) }
export function getBackupLog(id) { return api.get(`/backup/history/${id}/log`).then(r => r.data) }

// FTP 测试
export function testFtpConnection(data) { return api.post('/backup/test-ftp', data).then(r => r.data) }

// 本地文件浏览
export function getLocalFiles(path) { return api.get('/backup/local-files', { params: { path } }).then(r => r.data) }

// 下载 URL
export function getDownloadUrl(id) { return `/api/backup/history/${id}/download` }
