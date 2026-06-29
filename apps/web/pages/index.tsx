import { FormEvent, useEffect, useMemo, useState } from 'react';
import { apiDelete, apiGet, apiPost, apiPut, apiUrl } from '../lib/api';

type ReportField = {
  key: string;
  label: string;
  type: string;
  placeholder: string;
  help?: string;
  help_url?: string;
  required?: boolean;
  recommended?: boolean;
  group?: string;
};

type ReportWindow = {
  model?: string;
  summary?: string;
  recommended_start?: string;
  recommended_end?: string;
  needs_hot_collector?: boolean;
  collector_interval_minutes?: number;
};

type ReportOption = {
  name: string;
  title: string;
  default_env: string;
  fields: ReportField[];
  window?: ReportWindow;
};

type Subscription = {
  id: number;
  report_type: string;
  name: string;
  is_active: boolean;
  push_time: string;
  feishu_webhook: string;
  config: Record<string, string>;
  last_run_at?: string | null;
  last_status?: string;
  last_message?: string;
  warnings?: string[];
};

type RunLog = {
  id: number;
  subscription_id: number;
  report_type: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  output_path: string;
  message: string;
};

type SchedulerStatus = {
  enabled: boolean;
  timezone: string;
  jobs: { id: string; name: string; next_run_time: string | null }[];
};

const DEFAULT_TIMES: Record<string, string> = {
  ai: '07:50',
  wechat: '07:55',
  cctv: '08:00',
  astock: '08:15',
  douyin: '08:15',
  zsxq: '22:05',
  weibo: '22:30',
};

const REPORT_HINTS: Record<string, string> = {
  ai: 'AI 行业信息源聚合，适合早间浏览模型、Agent、产品和产业动态。',
  astock: 'A 股主题、机构和大 V 观点聚合；仅做信息摘要，不构成投资建议。',
  cctv: '抓取央视《朝闻天下》节目内容，按新闻板块整理。',
  douyin: '抖音热门作品榜聚合为热点话题，适合观察短视频平台情绪。',
  wechat: '公众号热门文章与关注作者日报，可维护关注账号列表。',
  weibo: '微博热搜聚类、官方简报补充与关注博主动态。',
  zsxq: '知识星球圈子内容，按精选内容与话题总结。',
};

function blankForm(reports: ReportOption[]) {
  const reportType = reports[0]?.name || 'wechat';
  return {
    report_type: reportType,
    name: reports[0]?.title || '',
    is_active: true,
    push_time: DEFAULT_TIMES[reportType] || '08:00',
    feishu_webhook: '',
    config: {} as Record<string, string>,
  };
}

export default function Home() {
  const [reports, setReports] = useState<ReportOption[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [runs, setRuns] = useState<RunLog[]>([]);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [form, setForm] = useState<ReturnType<typeof blankForm>>(blankForm([]));
  const [editingId, setEditingId] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [runningId, setRunningId] = useState<number | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [formError, setFormError] = useState('');

  const selectedReport = useMemo(
    () => reports.find((report) => report.name === form.report_type) || reports[0],
    [reports, form.report_type],
  );

  const reportTitle = (reportType: string) =>
    reports.find((report) => report.name === reportType)?.title || reportType;

  const credentialFields = useMemo(
    () => (selectedReport?.fields || []).filter((field) => field.group !== 'follow'),
    [selectedReport],
  );
  const followFields = useMemo(
    () => (selectedReport?.fields || []).filter((field) => field.group === 'follow'),
    [selectedReport],
  );

  function renderField(field: ReportField) {
    return (
      <label key={field.key}>
        <span className="field-label">
          {field.label}
          {field.required && <span className="field-required">*</span>}
          {!field.required && field.recommended && <span className="field-optional"> 建议填写</span>}
          {!field.required && !field.recommended && field.group === 'follow' && (
            <span className="field-optional"> 选填</span>
          )}
        </span>
        {field.type === 'textarea' ? (
          <textarea
            value={form.config[field.key] || ''}
            onChange={(event) => updateConfig(field.key, event.target.value)}
            placeholder={field.placeholder}
          />
        ) : (
          <input
            type={field.type === 'number' ? 'number' : field.type === 'password' ? 'password' : 'text'}
            autoComplete={field.type === 'password' ? 'off' : undefined}
            value={form.config[field.key] || ''}
            onChange={(event) => updateConfig(field.key, event.target.value)}
            placeholder={field.placeholder}
          />
        )}
        {field.help && (
          <span className="field-help">
            {field.help}
            {field.help_url && (
              <a className="field-help-link" href={field.help_url} target="_blank" rel="noreferrer">
                获取 Key
              </a>
            )}
          </span>
        )}
      </label>
    );
  }

  const pushTimeOutOfRange = useMemo(() => {
    const win = selectedReport?.window;
    if (!win?.recommended_start || !win?.recommended_end || !form.push_time) return false;
    const toMin = (value: string) => {
      const [h, m] = value.split(':').map(Number);
      return h * 60 + m;
    };
    const current = toMin(form.push_time);
    return current < toMin(win.recommended_start) || current > toMin(win.recommended_end);
  }, [selectedReport, form.push_time]);

  async function load() {
    const [reportData, subscriptionData, runData, schedulerData] = await Promise.all([
      apiGet<ReportOption[]>('/api/reports'),
      apiGet<Subscription[]>('/api/subscriptions'),
      apiGet<RunLog[]>('/api/runs?limit=20'),
      apiGet<SchedulerStatus>('/api/scheduler/status'),
    ]);
    setReports(reportData);
    setSubscriptions(subscriptionData);
    setRuns(runData);
    setScheduler(schedulerData);
    if (!form.name && reportData.length) setForm(blankForm(reportData));
  }

  useEffect(() => {
    load().catch((error) => setMessage(error.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function changeReportType(reportType: string) {
    const report = reports.find((item) => item.name === reportType);
    setFormError('');
    setForm({
      ...form,
      report_type: reportType,
      name: report?.title || reportType,
      push_time: DEFAULT_TIMES[reportType] || '08:00',
      config: {},
    });
  }

  function updateConfig(key: string, value: string) {
    setForm({ ...form, config: { ...form.config, [key]: value } });
  }

  function edit(item: Subscription) {
    setEditingId(item.id);
    setForm({
      report_type: item.report_type,
      name: item.name,
      is_active: item.is_active,
      push_time: item.push_time,
      feishu_webhook: item.feishu_webhook,
      config: item.config || {},
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function reset() {
    setEditingId(null);
    setFormError('');
    setForm(blankForm(reports));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const missing = (selectedReport?.fields || []).filter(
      (field) => field.required && !(form.config[field.key] || '').trim(),
    );
    if (missing.length) {
      setFormError(`请先填写必填项：${missing.map((field) => field.label).join('、')}`);
      return;
    }
    setFormError('');
    setBusy(true);
    setMessage('');
    try {
      const saved = editingId
        ? await apiPut<Subscription>(`/api/subscriptions/${editingId}`, form)
        : await apiPost<Subscription>('/api/subscriptions', form);
      const base = editingId ? '订阅已更新，后端定时任务已重新加载。' : '订阅已创建，后端定时任务已加载。';
      const warnings = saved.warnings || [];
      setMessage(warnings.length ? `${base}\n注意：\n- ${warnings.join('\n- ')}` : base);
      reset();
      await load();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(item: Subscription) {
    setTogglingId(item.id);
    setMessage('');
    try {
      await apiPut<Subscription>(`/api/subscriptions/${item.id}`, { is_active: !item.is_active });
      setMessage(item.is_active ? `「${reportTitle(item.report_type)}」已暂停。` : `「${reportTitle(item.report_type)}」已启用。`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setTogglingId(null);
    }
  }

  async function remove(item: Subscription) {
    if (!window.confirm(`删除订阅「${item.name}」？`)) return;
    await apiDelete(`/api/subscriptions/${item.id}`);
    await load();
  }

  async function runNow(item: Subscription) {
    setRunningId(item.id);
    setMessage(`「${item.name}」渲染测试运行中…`);
    try {
      const started = await apiPost<RunLog>(`/api/subscriptions/${item.id}/run`, {
        render_only: true,
        send: false,
      });
      const finished = await pollRun(started.id);
      if (!finished || finished.status === 'running') {
        setMessage('渲染测试仍在运行，可稍后在运行记录中查看结果。');
      } else if (finished.status === 'success') {
        setMessage('已完成渲染测试。');
      } else {
        setMessage(`测试失败：${finished.message}`);
      }
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setRunningId(null);
    }
  }

  async function pollRun(runId: number): Promise<RunLog | null> {
    const maxAttempts = 90;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      try {
        const log = await apiGet<RunLog>(`/api/runs/${runId}`);
        if (log.status !== 'running') return log;
      } catch {
        // transient error; keep polling
      }
    }
    return null;
  }

  return (
    <main className="app-shell">
      <section className="topbar">
        <div className="brand">
          <h1>DAILY-BRIEFING-BOT</h1>
          <p className="brand-tagline">
            自托管社媒日报工作台 · 7 套日报 · 定时推送飞书 · 凭证与关注内容可配
          </p>
        </div>
      </section>

      {message && <div className="notice">{message}</div>}

      <section className="workspace-grid">
        <form className="panel config-panel" onSubmit={submit}>
          <div className="panel-title">
            <div>
              <p className="eyebrow dark">{editingId ? 'Edit' : 'Create'}</p>
              <h2>{editingId ? '编辑订阅' : '新增日报订阅'}</h2>
            </div>
            {editingId && (
              <button type="button" className="ghost-button" onClick={reset}>
                取消编辑
              </button>
            )}
          </div>

          <label>
            日报类型
            <select value={form.report_type} onChange={(event) => changeReportType(event.target.value)}>
              {reports.map((report) => (
                <option key={report.name} value={report.name}>
                  {report.title}
                </option>
              ))}
            </select>
          </label>
          {selectedReport && (
            <p className="report-desc">{REPORT_HINTS[selectedReport.name] || selectedReport.default_env}</p>
          )}

          <div className="form-grid">
            <label>
              推送时间
              <input type="time" value={form.push_time} onChange={(event) => setForm({ ...form, push_time: event.target.value })} />
            </label>
            <label>
              是否启用订阅
              <span className="toggle-row">
                <span>{form.is_active ? '已启用' : '未启用'}</span>
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                />
              </span>
            </label>
          </div>
          {selectedReport?.window?.recommended_start && (
            <p className={`hint ${pushTimeOutOfRange ? 'hint-warn' : ''}`}>
              {selectedReport.window.summary} 建议推送时间 {selectedReport.window.recommended_start}–{selectedReport.window.recommended_end}。
              {pushTimeOutOfRange && ' 当前时间不在推荐区间，可能导致数据为空或过时。'}
              {selectedReport.window.needs_hot_collector &&
                ' 该日报会自动注册热搜采集任务（每 ' +
                  (selectedReport.window.collector_interval_minutes || 30) +
                  ' 分钟一次）。'}
            </p>
          )}

          <label>
            飞书 Webhook
            <input
              value={form.feishu_webhook}
              onChange={(event) => setForm({ ...form, feishu_webhook: event.target.value })}
              placeholder="请输入"
            />
          </label>

          {credentialFields.length > 0 && (
            <div className="field-section">
              <h3>凭证配置</h3>
              {credentialFields.map(renderField)}
            </div>
          )}

          {followFields.length > 0 && (
            <div className="field-section">
              <h3>关注内容配置</h3>
              <p className="hint">以下为选填项，留空对应模块将不会渲染。</p>
              {followFields.map(renderField)}
            </div>
          )}

          {formError && <p className="form-error">{formError}</p>}

          <button className="primary-button" type="submit" disabled={busy}>
            {busy ? '处理中...' : editingId ? '保存修改' : '创建订阅'}
          </button>
        </form>

        <section className="panel">
          <div className="panel-title">
            <div>
              <p className="eyebrow dark">Scheduler</p>
              <h2>已订阅日报</h2>
            </div>
            <span className="status-pill">{scheduler?.enabled ? '调度开启' : '调度关闭'}</span>
          </div>
          <div className="subscription-list">
            {subscriptions.length === 0 && <p className="empty">还没有订阅。</p>}
            {subscriptions.map((item) => (
              <article className="subscription-card" key={item.id}>
                <div>
                  <h3>{reportTitle(item.report_type)}</h3>
                  <p>
                    {item.report_type} · {item.push_time} · {item.is_active ? '已启用' : '已暂停'}
                  </p>
                  {item.last_status && <p className={`run-status ${item.last_status}`}>最近运行：{item.last_status}</p>}
                </div>
                <div className="card-actions">
                  <button
                    type="button"
                    className={item.is_active ? 'toggle-pause' : 'toggle-enable'}
                    onClick={() => toggleActive(item)}
                    disabled={togglingId !== null}
                  >
                    {togglingId === item.id ? '处理中…' : item.is_active ? '暂停' : '启用'}
                  </button>
                  <button type="button" onClick={() => runNow(item)} disabled={runningId !== null}>
                    {runningId === item.id ? '运行中…' : '渲染测试'}
                  </button>
                  <button type="button" onClick={() => edit(item)}>
                    编辑
                  </button>
                  <button type="button" className="danger" onClick={() => remove(item)}>
                    删除
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      </section>

      <section className="panel">
        <div className="panel-title">
          <div>
            <p className="eyebrow dark">Runs</p>
            <h2>运行记录</h2>
          </div>
          <span className="muted">{scheduler?.timezone || 'Asia/Shanghai'}</span>
        </div>
        <div className="run-grid">
          {runs.map((run) => (
            <article className="run-card" key={run.id}>
              <div>
                <strong>{run.report_type}</strong>
                <span className={`run-status ${run.status}`}>{run.status}</span>
              </div>
              <p>{new Date(run.started_at).toLocaleString()}</p>
              {run.output_path && (
                <a
                  href={apiUrl(`/api/runs/${run.id}/image?v=${encodeURIComponent(run.finished_at || run.started_at)}`)}
                  target="_blank"
                  rel="noreferrer"
                >
                  查看渲染图片
                </a>
              )}
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
