<script setup>
import { h, reactive, ref } from 'vue'
import { NButton, NCheckbox, NDataTable, NInput, NModal, NTag, useDialog, useMessage } from 'naive-ui'
import { api } from '../api'
import { isMobile, logout, state } from '../store'

const message = useMessage()
const dialog = useDialog()
document.title = '账号设置 · InStock'

// ---------- 修改自己的密码 ----------
const pwd = reactive({ old: '', next: '', confirm: '' })
const saving = ref(false)

async function changePassword() {
  if (!pwd.old || !pwd.next) return message.warning('请填写原密码和新密码')
  if (pwd.next !== pwd.confirm) return message.warning('两次输入的新密码不一致')
  saving.value = true
  try {
    await api.changePassword(pwd.old, pwd.next)
    Object.assign(pwd, { old: '', next: '', confirm: '' })
    message.success('密码已修改，其他设备上的登录已失效')
  } catch (e) {
    message.error(e.message)
  } finally {
    saving.value = false
  }
}

// ---------- 账号管理（管理员） ----------
const users = ref([])
const loading = ref(false)

async function loadUsers() {
  if (!state.user?.admin) return
  loading.value = true
  try {
    users.value = (await api.users()).items
  } catch (e) {
    message.error(`加载失败：${e.message}`)
  } finally {
    loading.value = false
  }
}

async function run(action, success) {
  try {
    await action()
    if (success) message.success(success)
    await loadUsers()
  } catch (e) {
    message.error(e.message)
  }
}

const creating = reactive({ show: false, username: '', password: '', admin: false })
function openCreate() {
  Object.assign(creating, { show: true, username: '', password: '', admin: false })
}
async function submitCreate() {
  await run(() => api.createUser({ username: creating.username, password: creating.password, admin: creating.admin }),
    `已创建账号 ${creating.username.trim().toLowerCase()}`)
  if (users.value.some((u) => u.username === creating.username.trim().toLowerCase())) creating.show = false
}

const resetting = reactive({ show: false, username: '', password: '' })
async function submitReset() {
  const { username, password } = resetting
  if (!password) return message.warning('请输入新密码')
  try {
    await api.updateUser(username, { password })
    resetting.show = false
    message.success(`已重置 ${username} 的密码，该账号需要重新登录`)
    await loadUsers()
  } catch (e) {
    message.error(e.message)
  }
}

function confirm(content, action, success) {
  dialog.warning({
    title: '请确认', content, positiveText: '确定', negativeText: '取消',
    onPositiveClick: () => run(action, success),
  })
}

const fmtTime = (v) => (v ? String(v).slice(0, 16) : '-')

const actions = (u) => {
  const self = u.username === state.user.username
  const btn = (label, onClick, props = {}) => h(NButton, { size: 'tiny', quaternary: true, onClick, ...props }, () => label)
  return h('div', { class: 'actions' }, [
    btn('重置密码', () => Object.assign(resetting, { show: true, username: u.username, password: '' })),
    !self && btn(u.admin ? '取消管理员' : '设为管理员', () => confirm(
      `${u.admin ? '取消' : '授予'} ${u.username} 的管理员权限？`,
      () => api.updateUser(u.username, { admin: !u.admin }), '已更新')),
    !self && u.sessions > 0 && btn('强制下线', () => confirm(
      `让 ${u.username} 在所有设备上退出登录？`, () => api.updateUser(u.username, { logout: true }), '已下线')),
    !self && btn('删除', () => confirm(
      `删除账号 ${u.username}？该账号的关注列表也会一并删除，且无法恢复。`, () => api.deleteUser(u.username), '已删除'),
    { type: 'error' }),
  ])
}

const columns = [
  { title: '账号', key: 'username', render: (u) => h('b', u.username) },
  { title: '角色', key: 'admin', width: 90,
    render: (u) => h(NTag, { size: 'small', bordered: false, type: u.admin ? 'warning' : 'default' },
      () => (u.admin ? '管理员' : '普通')) },
  { title: '已登录设备', key: 'sessions', width: 96 },
  { title: '最近使用', key: 'last_used', width: 150, render: (u) => fmtTime(u.last_used) },
  { title: '创建时间', key: 'created_at', width: 150, render: (u) => fmtTime(u.created_at) },
  { title: '操作', key: 'actions', render: actions },
]

function confirmLogout() {
  dialog.info({
    title: '退出登录', content: '退出后需要重新输入账号密码。', positiveText: '退出', negativeText: '取消',
    onPositiveClick: logout,
  })
}

loadUsers()
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <h1>账号设置</h1>
      <span class="spacer" />
      <NButton size="small" @click="confirmLogout">退出登录</NButton>
    </div>

    <section class="card">
      <div class="card-title">
        <span>当前账号：{{ state.user.username }}</span>
        <NTag size="small" :bordered="false" :type="state.user.admin ? 'warning' : 'default'">
          {{ state.user.admin ? '管理员' : '普通账号' }}
        </NTag>
      </div>
      <form class="card-body form" @submit.prevent="changePassword">
        <input type="text" autocomplete="username" :value="state.user.username" hidden readonly />
        <label>原密码<NInput v-model:value="pwd.old" type="password" show-password-on="click"
                            :input-props="{ autocomplete: 'current-password' }" /></label>
        <label>新密码<NInput v-model:value="pwd.next" type="password" show-password-on="click" placeholder="至少 8 位"
                            :input-props="{ autocomplete: 'new-password' }" /></label>
        <label>确认新密码<NInput v-model:value="pwd.confirm" type="password" show-password-on="click"
                              :input-props="{ autocomplete: 'new-password' }" /></label>
        <div class="form-foot">
          <NButton type="primary" attr-type="submit" :loading="saving">修改密码</NButton>
          <span class="muted small">修改后其他设备上的登录会全部失效，本设备保持登录。</span>
        </div>
      </form>
    </section>

    <section v-if="state.user.admin" class="card">
      <div class="card-title">
        <span>账号管理 <span class="muted small">每个账号有各自的关注列表</span></span>
        <NButton size="small" type="primary" secondary @click="openCreate">新建账号</NButton>
      </div>
      <NDataTable :columns="columns" :data="users" :loading="loading" :bordered="false" size="small"
                  :row-key="(u) => u.username" :scroll-x="isMobile ? 820 : undefined" />
    </section>

    <NModal v-model:show="creating.show" preset="card" title="新建账号" class="modal" :bordered="false">
      <form class="form" @submit.prevent="submitCreate">
        <label>账号<NInput v-model:value="creating.username" placeholder="2~32 位字母、数字或 _ . -"
                          :input-props="{ autocomplete: 'off', autocapitalize: 'off', spellcheck: false }" /></label>
        <label>初始密码<NInput v-model:value="creating.password" type="password" show-password-on="click"
                              placeholder="至少 8 位" :input-props="{ autocomplete: 'new-password' }" /></label>
        <NCheckbox v-model:checked="creating.admin">管理员（可管理所有账号）</NCheckbox>
        <div class="form-foot"><NButton type="primary" attr-type="submit">创建</NButton></div>
      </form>
    </NModal>

    <NModal v-model:show="resetting.show" preset="card" :title="`重置 ${resetting.username} 的密码`" class="modal"
            :bordered="false">
      <form class="form" @submit.prevent="submitReset">
        <label>新密码<NInput v-model:value="resetting.password" type="password" show-password-on="click"
                            placeholder="至少 8 位" :input-props="{ autocomplete: 'new-password' }" /></label>
        <p class="muted small">重置后该账号在所有设备上都需要用新密码重新登录。</p>
        <div class="form-foot"><NButton type="primary" attr-type="submit">重置</NButton></div>
      </form>
    </NModal>
  </div>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: 12px; max-width: 420px; }
.form label { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--muted); }
.form-foot { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.small { font-size: 12px; font-weight: 400; }
.modal { width: min(440px, calc(100vw - 32px)); }
.modal .form { max-width: none; }
:deep(.actions) { display: flex; flex-wrap: wrap; gap: 2px; }
</style>
