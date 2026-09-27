/* Dùng chung hộp thoại xác nhận cho mọi thao tác lưu / cập nhật / xóa. */
(function () {
  const style = document.createElement('style');
  style.textContent = `
    .ss-confirm-dialog{padding:0;border:0;background:transparent;max-width:min(420px,calc(100vw - 32px));max-height:calc(100vh - 32px);overflow:auto;color:var(--ss-text,#0f172a)}
    .ss-confirm-dialog::backdrop{background:rgba(15,23,42,.6)}
    .ss-confirm-box{box-sizing:border-box;background:var(--ss-card,#fff);color:var(--ss-text,#0f172a);width:100%;border-radius:16px;padding:24px;box-shadow:0 24px 60px rgba(0,0,0,.35);display:flex;flex-direction:column;gap:8px;animation:ss-pop .18s ease-out}
    .ss-confirm-box h2{margin:0;font-size:1.1rem}
    .ss-confirm-box p{margin:0;color:var(--ss-muted,#475569);white-space:pre-wrap;max-height:50vh;overflow:auto;line-height:1.5}
    .ss-confirm-box input{font:inherit;padding:10px;border:1px solid var(--ss-line,#cbd5e1);border-radius:10px;background:var(--ss-input,#fff);color:var(--ss-text,#0f172a)}
    .ss-confirm-box input:focus-visible,.ss-confirm-actions button:focus-visible{outline:2px solid #2563eb;outline-offset:2px}
    .ss-confirm-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:14px;flex-wrap:wrap}
    .ss-confirm-box *{box-sizing:border-box}
    .ss-confirm-actions button{font:inherit;padding:9px 18px;border-radius:10px;border:0;cursor:pointer;min-height:40px;white-space:nowrap}
    .ss-confirm-cancel{background:var(--ss-line,#e2e8f0);color:var(--ss-text,#0f172a)}
    .ss-confirm-ok{background:#2563eb;color:#fff}
    .ss-confirm-danger{background:#dc2626;color:#fff}
    .ss-confirm-box input[hidden],.ss-confirm-hint[hidden]{display:none}
    .ss-confirm-hint{margin:0;font-size:.8rem;color:var(--ss-muted,#64748b)}
    body.dark{--ss-card:#222a2e;--ss-text:#e7eef0;--ss-muted:#a7b6ba;--ss-line:#394448;--ss-input:#171d20}
    @keyframes ss-pop{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:none}}`;
  document.head.appendChild(style);

  // Dùng <dialog> native để vào top layer: luôn nằm trên mọi dialog/z-index khác.
  const dialog = document.createElement('dialog');
  dialog.className = 'ss-confirm-dialog';
  dialog.innerHTML = `<form method="dialog" class="ss-confirm-box" aria-labelledby="ss-confirm-title" aria-describedby="ss-confirm-message">
    <h2 id="ss-confirm-title"></h2>
    <p id="ss-confirm-message"></p>
    <input type="text" hidden>
    <p class="ss-confirm-hint" hidden>Enter để xác nhận · Esc để hủy</p>
    <div class="ss-confirm-actions">
      <button type="button" class="ss-confirm-cancel">Hủy</button>
      <button type="button" class="ss-confirm-ok">Xác nhận</button>
    </div>
  </form>`;
  document.body.appendChild(dialog);

  const box = dialog.querySelector('.ss-confirm-box');
  if (box) box.addEventListener('submit', (event) => event.preventDefault());
  const titleEl = dialog.querySelector('h2');
  const messageEl = dialog.querySelector('#ss-confirm-message');
  const hintEl = dialog.querySelector('.ss-confirm-hint');
  const inputEl = dialog.querySelector('input');
  const okBtn = dialog.querySelector('.ss-confirm-ok');
  const cancelBtn = dialog.querySelector('.ss-confirm-cancel');
  let resolver = null;
  let lastFocused = null;

  function close(result) {
    if (resolver === null && !dialog.open) return;
    if (dialog.open) dialog.close();
    inputEl.value = '';
    const resolve = resolver;
    resolver = null;
    if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
    lastFocused = null;
    if (resolve) resolve(result);
  }

  dialog.addEventListener('close', () => { if (resolver) close(false); });
  dialog.addEventListener('click', (event) => { if (event.target === dialog) close(false); });
  cancelBtn.addEventListener('click', () => close(false));
  okBtn.addEventListener('click', () => close(inputEl.hidden ? true : inputEl.value));
  inputEl.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') { event.preventDefault(); close(inputEl.value); }
  });

  function open({ title, message, okText = 'Xác nhận', cancelText = 'Hủy', danger = false, input = null, initialValue = '' }) {
    if (dialog.open) close(false);
    lastFocused = document.activeElement;
    titleEl.textContent = title;
    messageEl.textContent = message;
    okBtn.textContent = okText;
    cancelBtn.textContent = cancelText;
    okBtn.className = danger ? 'ss-confirm-ok ss-confirm-danger' : 'ss-confirm-ok';
    inputEl.hidden = !input;
    inputEl.value = initialValue;
    inputEl.placeholder = input || '';
    hintEl.hidden = !input;
    dialog.showModal();
    if (input) inputEl.focus();
    else okBtn.focus();
    return new Promise((resolve) => { resolver = resolve; });
  }

  window.studySyncConfirm = {
    open,
    confirm: (message, title = 'Xác nhận', options = {}) => open({ title, message, ...options }),
    alert: (message, title = 'Thông báo') => open({ title, message, okText: 'Đã hiểu' }),
    prompt: (message, title = 'Nhập nội dung', options = {}) => open({ title, message, ...options, input: options.input || '' }),
  };
})();

