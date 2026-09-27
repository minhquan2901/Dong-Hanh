/* Dùng chung hộp thoại xác nhận cho mọi thao tác lưu / cập nhật / xóa. */
(function () {
  const style = document.createElement('style');
  style.textContent = `
    .ss-confirm-backdrop{position:fixed;inset:0;background:#0f172a99;display:grid;place-items:center;z-index:1000;padding:20px}
    .ss-confirm-backdrop[hidden]{display:none}
    .ss-confirm-box{background:#fff;max-width:420px;width:100%;border-radius:16px;padding:24px;box-shadow:0 24px 60px #0f172a55;display:flex;flex-direction:column;gap:8px}
    .ss-confirm-box h2{margin:0;font-size:1.1rem}
    .ss-confirm-box p{margin:0;color:#475569;white-space:pre-wrap;max-height:50vh;overflow:auto}
    .ss-confirm-box input{font:inherit;padding:10px;border:1px solid #cbd5e1;border-radius:10px}
    .ss-confirm-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:14px}
    .ss-confirm-actions button{font:inherit;padding:9px 18px;border-radius:10px;border:0;cursor:pointer}
    .ss-confirm-cancel{background:#e2e8f0;color:#0f172a}
    .ss-confirm-ok{background:#2563eb;color:#fff}
    .ss-confirm-danger{background:#dc2626;color:#fff}`;
  document.head.appendChild(style);

  function build() {
    const backdrop = document.createElement('div');
    backdrop.className = 'ss-confirm-backdrop';
    backdrop.hidden = true;
    backdrop.innerHTML = `<div class="ss-confirm-box" role="alertdialog" aria-modal="true" aria-labelledby="ss-confirm-title">
      <h2 id="ss-confirm-title"></h2><p></p><input type="text" hidden>
      <div class="ss-confirm-actions"><button type="button" class="ss-confirm-cancel">Hủy</button><button type="button" class="ss-confirm-ok">Xác nhận</button></div>
    </div>`;
    document.body.appendChild(backdrop);
    return backdrop;
  }

  const backdrop = build();
  const titleEl = backdrop.querySelector('h2');
  const messageEl = backdrop.querySelector('p');
  const inputEl = backdrop.querySelector('input');
  const okBtn = backdrop.querySelector('.ss-confirm-ok');
  const cancelBtn = backdrop.querySelector('.ss-confirm-cancel');
  let resolver = null;

  function close(result) {
    backdrop.hidden = true;
    inputEl.value = '';
    const resolve = resolver;
    resolver = null;
    if (resolve) resolve(result);
  }

  backdrop.addEventListener('click', (event) => { if (event.target === backdrop) close(false); });
  cancelBtn.addEventListener('click', () => close(false));
  okBtn.addEventListener('click', () => close(inputEl.hidden ? true : inputEl.value));
  inputEl.addEventListener('keydown', (event) => { if (event.key === 'Enter') close(inputEl.value); });

  function open({ title, message, okText = 'Xác nhận', cancelText = 'Hủy', danger = false, input = null, initialValue = '' }) {
    if (resolver) close(false);
    titleEl.textContent = title;
    messageEl.textContent = message;
    okBtn.textContent = okText;
    cancelBtn.textContent = cancelText;
    okBtn.className = danger ? 'ss-confirm-ok ss-confirm-danger' : 'ss-confirm-ok';
    inputEl.hidden = !input;
    inputEl.placeholder = input || '';
    inputEl.value = initialValue;
    backdrop.hidden = false;
    if (input) inputEl.focus();
    else okBtn.focus();
    return new Promise((resolve) => { resolver = resolve; });
  }

  window.studySyncConfirm = {
    open,
    confirm: (message, title = 'Xác nhận', options = {}) => open({ title, message, ...options }),
    alert: (message, title = 'Thông báo') => open({ title, message, okText: 'Đã hiểu' }),
    prompt: (message, title = 'Nhập nội dung', options = {}) => open({ title, message, input: options.input || '', ...options }),
  };
})();
