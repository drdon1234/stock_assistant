<script setup>
import { ref } from 'vue'
import { NAlert, NButton, NInput } from 'naive-ui'
import { login, state } from '../store'

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
document.title = '登录 · InStock'

async function submit() {
  if (!username.value.trim() || !password.value) {
    error.value = '请输入账号和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await login(username.value, password.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <form class="card panel" @submit.prevent="submit">
      <div class="brand">
        <img src="/favicon.svg" alt="" width="40" height="40" />
        <h1>InStock</h1>
      </div>
      <NAlert v-if="state.setup" type="warning" :show-icon="false" class="setup">
        还没有创建任何账号。请在服务器上运行
        <code>python -m instock user add 账号</code>，Docker 部署运行
        <code>docker exec -it instock-web python -m instock user add 账号</code>。第一个账号自动成为管理员。
      </NAlert>
      <NInput v-model:value="username" size="large" placeholder="账号" autofocus
              :input-props="{ autocomplete: 'username', autocapitalize: 'off', spellcheck: false }" />
      <NInput v-model:value="password" size="large" type="password" show-password-on="click" placeholder="密码"
              :input-props="{ autocomplete: 'current-password' }" />
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <NButton type="primary" size="large" block attr-type="submit" :loading="loading">登录</NButton>
      <p class="muted hint">
        登录后本设备会保持登录{{ state.sessionDays ? ` ${state.sessionDays} 天` : '' }}，期间每次访问自动续期。
        公用电脑用完请在右上角账号菜单中退出。
      </p>
    </form>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background: var(--bg);
}
.panel { width: 100%; max-width: 360px; padding: 28px 24px 20px; display: flex; flex-direction: column; gap: 14px; }
.brand { display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 4px; }
.brand h1 { margin: 0; font-size: 22px; font-weight: 700; }
.setup { font-size: 13px; line-height: 1.7; }
.setup code { font-size: 12px; word-break: break-all; }
.error { margin: 0; color: var(--up); font-size: 13px; }
.hint { margin: 0; font-size: 12px; line-height: 1.6; }
</style>
