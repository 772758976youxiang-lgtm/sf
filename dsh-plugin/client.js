window.__ModuleLoader__.load({
  id: '@local/dsh-sf-express',
  factory(require) {
    const React = require('react');
    const h = React.createElement;
    const { useState, useEffect } = React;
    const NS = 'settings.sfExpress';
    const SETTINGS = 'sf-express-settings';
    const refs = { sandbox: 'SF_DSH_SANDBOX_CREDENTIALS', production: 'SF_DSH_PRODUCTION_CREDENTIALS' };
    const zh = {
      title: '顺丰速运', intro: '配置顺丰接口后，新建任务选择“顺丰速运”预设，即可通过对话下单、查件和取消。',
      environment: '运行环境', sandbox: '沙盒环境', production: '生产环境', current: '当前生效：',
      partner: '顾客编码', checkword: '校验码', signMode: '数字签名方式', simple: '简易 MD5', standard: '标准 MD5',
      configured: '凭据已保存', missing: '尚未配置凭据', keep: '留空保留已保存的凭据', enter: '请填写此环境的凭据',
      save: '保存并启用此环境', clear: '清除此环境凭据', saving: '正在保存…', saved: '已保存，下一次工具调用生效。',
      cleared: '此环境的凭据已清除。', pair: '修改凭据时，请同时填写顾客编码和校验码。',
      length: '顾客编码或校验码长度超出限制。', loading: '正在读取配置…', retry: '重新读取',
      productionNote: '生产环境会创建或取消真实订单。Agent 会在操作前核对信息并确认。',
      sandboxNote: '沙盒环境用于接口测试，需使用该应用的沙盒校验码。',
      storage: '两套环境的凭据分别保存在 DSH 本机凭据库，重启后仍然有效；校验码不会回显。',
      mapping: '客户订单号自动生成；运单号与订单号的对应关系保留 24 小时。',
      unavailable: '顺丰插件配置尚未就绪，请重启 DSH 后重试。',
    };
    const en = {
      title: 'SF Express', intro: 'Configure SF, then select the SF Express preset for a new task to create, track, and cancel shipments.',
      environment: 'Environment', sandbox: 'Sandbox', production: 'Production', current: 'Active: ',
      partner: 'Partner ID', checkword: 'Checkword', signMode: 'Signature', simple: 'Simple MD5', standard: 'Standard MD5',
      configured: 'Credentials saved', missing: 'Credentials not configured', keep: 'Leave both blank to keep saved credentials', enter: 'Enter credentials for this environment',
      save: 'Save and activate', clear: 'Clear credentials', saving: 'Saving…', saved: 'Saved. Applies to the next tool call.',
      cleared: 'Credentials cleared.', pair: 'Enter both Partner ID and Checkword when replacing credentials.',
      length: 'Partner ID or Checkword is too long.', loading: 'Loading configuration…', retry: 'Reload',
      productionNote: 'Production creates or cancels real orders. The agent checks details and asks for confirmation before acting.',
      sandboxNote: 'Use the sandbox checkword for this SF application.',
      storage: 'Credentials are stored separately in the local DSH credential store and survive restarts. Checkwords are never returned.',
      mapping: 'Customer order IDs are generated automatically. Waybill mappings are retained for 24 hours.',
      unavailable: 'SF settings are not ready. Restart DSH and retry.',
    };
    const css = `
      .sf-dsh-page{display:flex;flex-direction:column;gap:16px;max-width:720px;color:var(--dsw-alias-label-primary);font-size:13px}
      .sf-dsh-page h2{font-size:18px;font-weight:600;margin:0}
      .sf-dsh-page p{margin:0;line-height:1.6;color:var(--dsw-alias-label-tertiary)}
      .sf-dsh-card{display:grid;gap:16px;padding:18px;border:1px solid var(--dsw-alias-border-l4);border-radius:14px;background:var(--dsw-alias-bg-module-platform)}
      .sf-dsh-field{display:grid;gap:7px;font-weight:500}
      .sf-dsh-field input,.sf-dsh-field select{width:100%;box-sizing:border-box;font:inherit;color:var(--dsw-alias-label-primary);background:var(--dsw-alias-bg-base);border:1px solid var(--dsw-alias-border-l4);border-radius:9px;padding:10px 12px;min-height:40px}
      .sf-dsh-field input:focus,.sf-dsh-field select:focus{outline:2px solid var(--dsw-alias-label-secondary);outline-offset:1px}
      .sf-dsh-actions{display:flex;gap:10px;flex-wrap:wrap}
      .sf-dsh-page button{font:inherit;border:1px solid var(--dsw-alias-border-l4);border-radius:9px;padding:9px 14px;cursor:pointer;background:var(--dsw-alias-bg-base);color:var(--dsw-alias-label-primary)}
      .sf-dsh-page button:disabled{opacity:.5;cursor:default}
      .sf-dsh-status{font-weight:600;line-height:1.6}
      .sf-dsh-note{padding:12px 14px;border:1px solid var(--dsw-alias-border-l4);border-radius:10px;line-height:1.6}
    `;
    const unwrap = result => {
      if (!result.ok) throw new Error(result.error?.message || 'DSH request failed');
      return result.value;
    };
    function SettingsPage({ t, api }) {
      const [view, setView] = useState(null);
      const [info, setInfo] = useState({});
      const [environment, setEnvironment] = useState('sandbox');
      const [sign, setSign] = useState('simple');
      const [partner, setPartner] = useState('');
      const [checkword, setCheckword] = useState('');
      const [busy, setBusy] = useState(true);
      const [message, setMessage] = useState('');
      async function load(preferred) {
        const data = unwrap(await api.settings.describe());
        const row = data.namespaces.find(item => item.ns === SETTINGS);
        if (!row) throw new Error(t('unavailable'));
        const credentials = unwrap(await api.credentials.describe(Object.values(refs)));
        const selected = preferred || row.value.environment;
        setView(row); setInfo(credentials); setEnvironment(selected);
        setSign(selected === 'production' ? row.value.productionSignMode : row.value.sandboxSignMode);
      }
      useEffect(() => { let alive = true; load().catch(error => { if (alive) setMessage(error.message); }).finally(() => { if (alive) setBusy(false); }); return () => { alive = false; }; }, []);
      async function save(event) {
        event.preventDefault();
        const id = partner.trim(), secret = checkword.trim();
        if (Boolean(id) !== Boolean(secret)) { setMessage(t('pair')); return; }
        if (id.length > 128 || secret.length > 256) { setMessage(t('length')); return; }
        if (!id && !info[refs[environment]]?.configured) { setMessage(t('enter')); return; }
        setBusy(true); setMessage(t('saving'));
        try {
          if (id) unwrap(await api.credentials.set(refs[environment], JSON.stringify({ partner_id: id, checkword: secret })));
          unwrap(await api.settings.update(SETTINGS, {
            environment, [environment === 'production' ? 'productionSignMode' : 'sandboxSignMode']: sign,
          }, view.revision));
          setPartner(''); setCheckword('');
          await load(environment); setMessage(t('saved'));
        } catch (error) { setMessage(error.message); }
        finally { setCheckword(''); setBusy(false); }
      }
      async function clear() {
        setBusy(true);
        try { unwrap(await api.credentials.unset(refs[environment])); await load(environment); setPartner(''); setCheckword(''); setMessage(t('cleared')); }
        catch (error) { setMessage(error.message); }
        finally { setBusy(false); }
      }
      const configured = info[refs[environment]]?.configured;
      const writable = info[refs[environment]]?.writable !== false;
      const field = (label, node) => h('label', { className: 'sf-dsh-field' }, label, node);
      return h('section', { className: 'sf-dsh-page' },
        h('style', null, css), h('h2', null, t('title')), h('p', null, t('intro')),
        view && h('div', { className: 'sf-dsh-status' }, t('current') + t(view.value.environment)),
        !view ? h('div', null, busy ? t('loading') : h('button', { onClick: () => { setBusy(true); load().catch(e => setMessage(e.message)).finally(() => setBusy(false)); } }, t('retry'))) :
        h('form', { className: 'sf-dsh-card', onSubmit: save, autoComplete: 'off' },
          field(t('environment'), h('select', { value: environment, disabled: busy, onChange: e => { const next = e.target.value; setEnvironment(next); setSign(next === 'production' ? view.value.productionSignMode : view.value.sandboxSignMode); setPartner(''); setCheckword(''); setMessage(''); } },
            h('option', { value: 'sandbox' }, t('sandbox')), h('option', { value: 'production' }, t('production')))),
          h('div', { className: 'sf-dsh-note' }, t(environment === 'production' ? 'productionNote' : 'sandboxNote')),
          h('div', { className: 'sf-dsh-status' }, t(configured ? 'configured' : 'missing')),
          field(t('partner'), h('input', { value: partner, disabled: busy || !writable, maxLength: 128, autoComplete: 'off', placeholder: t(configured ? 'keep' : 'enter'), onChange: e => setPartner(e.target.value) })),
          field(t('checkword'), h('input', { type: 'password', value: checkword, disabled: busy || !writable, maxLength: 256, autoComplete: 'new-password', placeholder: t(configured ? 'keep' : 'enter'), onChange: e => setCheckword(e.target.value) })),
          field(t('signMode'), h('select', { value: sign, disabled: busy, onChange: e => setSign(e.target.value) }, h('option', { value: 'simple' }, t('simple')), h('option', { value: 'standard' }, t('standard')))),
          h('div', { className: 'sf-dsh-actions' }, h('button', { type: 'submit', disabled: busy }, t('save')), h('button', { type: 'button', disabled: busy || !configured || !writable, onClick: clear }, t('clear')))),
        h('div', { role: 'status', 'aria-live': 'polite' }, message), h('p', null, t('storage')), h('p', null, t('mapping')));
    }
    return {
      inject: ['slots', 'locale', 'remote', 'remote.settings', 'remote.credentials'],
      apply(ctx) {
        ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'sf-express: locale');
        ctx.slots.inject('settings.section', () => ctx.slots.register({
          name: 'settings.section', id: 'sf-express', order: 25, locale: NS,
          label: () => ctx.locale.bind(NS)('title'), inject: () => ({ api: ctx.remote }),
        }, SettingsPage));
      },
    };
  },
});
