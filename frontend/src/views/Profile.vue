<template>
  <div class="profile">
    <div class="page-header"><h2>个人设置</h2></div>
    <div class="profile-grid">
      <el-card class="profile-card">
        <template #header><span>基本信息</span></template>
        <el-form :model="form" ref="formRef" label-width="80px">
          <el-form-item label="头像">
            <div class="avatar-section">
              <el-avatar :size="64" :src="avatarKey ? authStore.user?.avatar_url + '?t=' + avatarKey : authStore.user?.avatar_url">
                {{ (form.name || authStore.user?.username)?.charAt(0)?.toUpperCase() }}
              </el-avatar>
              <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="onFileChange" />
              <el-button size="small" style="margin-left:12px" @click="$refs.fileInput.click()">选择头像</el-button>
            </div>
          </el-form-item>
          <el-form-item label="用户名"><el-input :model-value="authStore.user?.username" disabled /></el-form-item>
          <el-form-item label="工号"><el-input :model-value="authStore.user?.gh" disabled /></el-form-item>
          <el-form-item label="角色">
            <el-tag :type="authStore.isAdmin?'danger':authStore.user?.role==='dept_admin'?'warning':'info'" size="small">
              {{ authStore.isAdmin?'管理员':authStore.user?.role==='dept_admin'?'部门管理员':'普通用户' }}
            </el-tag>
          </el-form-item>
          <el-form-item label="所属部门">
            <el-input :model-value="authStore.user?.department_name||'未分配'" disabled />
          </el-form-item>
          <el-form-item label="姓名"><el-input v-model="form.name" placeholder="请输入姓名" /></el-form-item>
          <el-form-item label="性别">
            <el-select v-model="form.gender" placeholder="请选择" clearable style="width:100%">
              <el-option label="男" value="男" /><el-option label="女" value="女" />
            </el-select>
          </el-form-item>
          <el-form-item label="邮箱"><el-input v-model="form.email" placeholder="请输入邮箱" /></el-form-item>
          <el-form-item label="办公电话"><el-input v-model="form.phone" placeholder="请输入办公电话" /></el-form-item>
          <el-form-item label="移动电话"><el-input v-model="form.mobile" placeholder="请输入移动电话" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" placeholder="备注信息" /></el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card class="password-card">
        <template #header><span>修改密码</span></template>
        <el-form :model="pwdForm" :rules="pwdRules" ref="pwdFormRef" label-width="80px">
          <el-form-item label="原密码" prop="old_password">
            <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="请输入原密码" />
          </el-form-item>
          <el-form-item label="新密码" prop="new_password">
            <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="请输入新密码" />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirm_password">
            <el-input v-model="pwdForm.confirm_password" type="password" show-password placeholder="请再次输入新密码" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleChangePassword" :loading="changingPwd">修改密码</el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </div>

    <!-- 头像裁剪对话框 -->
    <el-dialog v-model="cropVisible" title="裁剪头像（1:1）" width="460px" :close-on-click-modal="false">
      <div style="text-align:center;position:relative;overflow:hidden;user-select:none"
           ref="cropArea" @mousedown="onCropMouseDown" @mousemove="onCropMouseMove" @mouseup="onCropMouseUp"
           @touchstart="onCropTouch" @touchmove="onCropTouch" @touchend="onCropMouseUp">
        <canvas ref="cropCanvas" style="max-width:100%;cursor:move"></canvas>
      </div>
      <div style="margin-top:8px;color:#909399;font-size:12px;text-align:center">拖动图片调整裁剪范围</div>
      <template #footer>
        <el-button @click="cropVisible=false">取消</el-button>
        <el-button type="primary" @click="doCrop" :loading="cropUploading">确认裁剪</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick } from 'vue'
import { useAuthStore } from '@/store/auth'
import { updateProfile, changePassword } from '@/api/auth'
import api from '@/api'
import { ElMessage } from 'element-plus'

const authStore = useAuthStore()
const avatarKey = ref(0)

const formRef = ref(null)
const saving = ref(false)
const form = reactive({
  name: authStore.user?.name || '',
  email: authStore.user?.email || '',
  phone: authStore.user?.phone || '',
  mobile: authStore.user?.mobile || '',
  gender: authStore.user?.gender || '',
  notes: authStore.user?.notes || '',
})

// ── 头像裁剪（可拖动选区） ──
const cropVisible = ref(false)
const cropCanvas = ref(null)
const cropArea = ref(null)
const cropUploading = ref(false)
let cropImage = null
let cropX = 0, cropY = 0, cropSize = 200  // 选区位置和大小（图片坐标）
let dragging = false, dragStart = { x: 0, y: 0 }, cropStart = { x: 0, y: 0 }
let displayScale = 1  // 显示比例

function onFileChange(e) {
  const file = e.target.files[0]
  if (!file) return
  if (!file.type.startsWith('image/')) { ElMessage.error('只能上传图片'); return }
  if (file.size > 2*1024*1024) { ElMessage.error('图片不能超过2MB'); return }
  const reader = new FileReader()
  reader.onload = (ev) => {
    cropImage = new Image()
    cropImage.onload = async () => {
      cropVisible.value = true
      await nextTick()
      initCrop()
    }
    cropImage.src = ev.target.result
  }
  reader.readAsDataURL(file)
  e.target.value = ''
}

function initCrop() {
  if (!cropImage || !cropCanvas.value) return
  const canvas = cropCanvas.value
  const maxW = 400
  displayScale = Math.min(maxW / cropImage.width, 1)
  const w = Math.round(cropImage.width * displayScale)
  const h = Math.round(cropImage.height * displayScale)
  canvas.width = w
  canvas.height = h
  cropSize = Math.min(cropImage.width, cropImage.height)
  cropX = (cropImage.width - cropSize) / 2
  cropY = (cropImage.height - cropSize) / 2
  drawCrop()
}

function drawCrop() {
  const canvas = cropCanvas.value
  if (!canvas || !cropImage) return
  const ctx = canvas.getContext('2d')
  const w = canvas.width, h = canvas.height
  // 绘制图片
  ctx.clearRect(0, 0, w, h)
  ctx.drawImage(cropImage, 0, 0, w, h)
  // 半透明遮罩（选区外）
  const cx = cropX * displayScale, cy = cropY * displayScale, cs = cropSize * displayScale
  ctx.fillStyle = 'rgba(0,0,0,0.45)'
  ctx.fillRect(0, 0, w, cy)           // 上
  ctx.fillRect(0, cy, cx, cs)          // 左
  ctx.fillRect(cx + cs, cy, w - cx - cs, cs) // 右
  ctx.fillRect(0, cy + cs, w, h - cy - cs)   // 下
  // 选区边框
  ctx.strokeStyle = '#409eff'
  ctx.lineWidth = 2
  ctx.strokeRect(cx, cy, cs, cs)
}

function getCanvasPos(e) {
  const rect = cropCanvas.value.getBoundingClientRect()
  const clientX = e.touches ? e.touches[0].clientX : e.clientX
  const clientY = e.touches ? e.touches[0].clientY : e.clientY
  return { x: clientX - rect.left, y: clientY - rect.top }
}

function onCropMouseDown(e) { startDrag(getCanvasPos(e)) }
function onCropTouch(e) { e.preventDefault(); startDrag(getCanvasPos(e)) }

function startDrag(pos) {
  dragging = true
  dragStart = { x: pos.x, y: pos.y }
  cropStart = { x: cropX, y: cropY }
}

function onCropMouseMove(e) { if (dragging) doDrag(getCanvasPos(e)) }
function onCropMouseUp() { dragging = false }

function doDrag(pos) {
  const dx = (pos.x - dragStart.x) / displayScale
  const dy = (pos.y - dragStart.y) / displayScale
  cropX = Math.max(0, Math.min(cropImage.width - cropSize, cropStart.x + dx))
  cropY = Math.max(0, Math.min(cropImage.height - cropSize, cropStart.y + dy))
  drawCrop()
}

async function doCrop() {
  const canvas = cropCanvas.value
  if (!canvas) return
  cropUploading.value = true
  try {
    // 创建裁切后的 canvas
    const out = document.createElement('canvas')
    out.width = 200; out.height = 200
    out.getContext('2d').drawImage(cropImage, cropX, cropY, cropSize, cropSize, 0, 0, 200, 200)
    const blob = await new Promise(resolve => out.toBlob(resolve, 'image/jpeg', 0.85))
    const fd = new FormData(); fd.append('file', blob, 'avatar.jpg')
    const { data } = await api.post('/auth/avatar', fd)
    avatarKey.value = Date.now()
    localStorage.setItem('avatarVer', String(Date.now()))
    const updated = await updateProfile({ avatar_url: data.avatar_url })
    authStore.user = updated
    localStorage.setItem('user', JSON.stringify(updated))
    ElMessage.success('头像已更新')
    cropVisible.value = false
  } catch (e) { ElMessage.error(e.response?.data?.detail || '上传失败') }
  finally { cropUploading.value = false }
}

// ── 保存信息 ──
async function handleSave() {
  saving.value = true
  try {
    const payload = {}
    for (const k of ['email','name','phone','mobile','gender','notes'])
      if (form[k] !== void 0) payload[k] = form[k] || null
    const updated = await updateProfile(payload)
    authStore.user = updated
    localStorage.setItem('user', JSON.stringify(updated))
    avatarKey.value = Date.now()
    ElMessage.success('保存成功')
  } catch (e) { ElMessage.error(e.response?.data?.detail || '保存失败') } finally { saving.value = false }
}

// ── 修改密码 ──
const pwdFormRef = ref(null)
const changingPwd = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const validateConfirm = (_rule, value, callback) => {
  if (value !== pwdForm.new_password) callback(new Error('两次密码输入不一致'))
  else callback()
}
const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [{ required: true, message: '请输入新密码', trigger: 'blur' }],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' },
  ],
}
async function handleChangePassword() {
  try { await pwdFormRef.value.validate() } catch { return }
  changingPwd.value = true
  try {
    await changePassword(pwdForm.old_password, pwdForm.new_password)
    ElMessage.success('密码修改成功')
    pwdForm.old_password = ''; pwdForm.new_password = ''; pwdForm.confirm_password = ''
    pwdFormRef.value.resetFields()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '修改失败') } finally { changingPwd.value = false }
}
</script>

<style scoped>
.page-header { margin-bottom: 24px; }
.page-header h2 { margin: 0; font-size: 22px; font-weight: 700; }
.profile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 960px; }
@media (max-width: 768px) { .profile-grid { grid-template-columns: 1fr; } }
.avatar-section { display: flex; align-items: center; }
</style>
