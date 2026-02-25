import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchJSON, wsURL } from '../api';

function nextCategoryId(draft) {
  const ids = Object.keys(draft)
    .map((key) => Number(key))
    .filter((n) => Number.isFinite(n) && n > 0);
  if (!ids.length) {
    return '1';
  }
  return String(Math.max(...ids) + 1);
}

export default function SuggestPage() {
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState('');
  const [connected, setConnected] = useState(false);

  const [suggestions, setSuggestions] = useState({});
  const [draft, setDraft] = useState({});
  const [error, setError] = useState('');
  const [applyNotice, setApplyNotice] = useState('');
  const [codexNotice, setCodexNotice] = useState('');
  const [launchingCodex, setLaunchingCodex] = useState(false);

  const wsRef = useRef(null);

  useEffect(() => {
    async function loadProjects() {
      try {
        const data = await fetchJSON('/api/projects');
        setProjects(data.projects || []);
        if (data.projects?.length) {
          setProject((prev) => prev || data.projects[0].id);
        }
      } catch (err) {
        setError(String(err.message || err));
      }
    }

    loadProjects();
  }, []);

  useEffect(() => {
    if (!project) {
      return;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setSuggestions({});
    setDraft({});
    setApplyNotice('');
    setCodexNotice('');
    setError('');

    const socket = new WebSocket(wsURL(`/ws/suggest/${project}`));
    wsRef.current = socket;

    socket.onopen = () => {
      setConnected(true);
    };

    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);

      if (payload.type === 'snapshot') {
        setSuggestions(payload.suggestions || {});
        setDraft(payload.draft_categories || {});
        setError('');
        return;
      }

      if (payload.type === 'draft_updated') {
        setDraft(payload.draft_categories || {});
        return;
      }

      if (payload.type === 'applied') {
        setApplyNotice(
          `已写入 ${payload.projects_yaml}（项目: ${payload.project}，分类数: ${Object.keys(
            payload.categories || {}
          ).length}）`
        );
        setDraft(payload.categories || {});
        return;
      }

      if (payload.type === 'error') {
        setError(payload.message || '会话异常');
      }
    };

    socket.onclose = () => {
      setConnected(false);
    };

    socket.onerror = () => {
      setConnected(false);
      setError('Suggest WebSocket 连接失败');
    };

    return () => {
      socket.close();
    };
  }, [project]);

  const suggestedCategories = useMemo(
    () => suggestions.suggested_categories || {},
    [suggestions]
  );

  const paperClassifications = useMemo(
    () => suggestions.paper_classifications || [],
    [suggestions]
  );

  const pushDraft = (nextDraft) => {
    setDraft(nextDraft);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'set_draft', draft_categories: nextDraft }));
    }
  };

  const updateCategoryLabel = (id, value) => {
    const next = { ...draft, [id]: value };
    pushDraft(next);
  };

  const removeCategory = (id) => {
    const next = { ...draft };
    delete next[id];
    pushDraft(next);
  };

  const addCategory = () => {
    const id = nextCategoryId(draft);
    pushDraft({ ...draft, [id]: '新类别' });
  };

  const applyCategories = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError('会话未连接，无法写入配置');
      return;
    }

    wsRef.current.send(
      JSON.stringify({
        type: 'apply',
        run_classify: false,
        draft_categories: draft
      })
    );
  };

  const openCodexTerminal = async () => {
    if (!project) {
      setError('请先选择项目');
      return;
    }

    setError('');
    setLaunchingCodex(true);
    setCodexNotice('');

    try {
      const result = await fetchJSON('/api/codex/open', {
        method: 'POST',
        body: JSON.stringify({ project })
      });
      setCodexNotice(
        `已打开 Codex 终端（项目: ${result.project}）。先确认标签，再由 Codex 直接写 JSON 并移动 Markdown（不运行 main.py classify）。`
      );
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLaunchingCodex(false);
    }
  };

  return (
    <section className="stage-page">
      <div className="panel control-panel">
        <div className="control-grid suggest-control-grid">
          <label>
            项目
            <select value={project} onChange={(e) => setProject(e.target.value)}>
              {projects.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.id})
                </option>
              ))}
            </select>
          </label>
          <div className="tag-list">
            <span className={`status-badge ${connected ? 'status-success' : 'status-failed'}`}>
              {connected ? '会话已连接' : '会话未连接'}
            </span>
          </div>
          <button className="primary-btn" onClick={openCodexTerminal} disabled={launchingCodex}>
            {launchingCodex ? '启动中...' : '打开 Codex 终端'}
          </button>
          <button className="secondary-btn" onClick={applyCategories}>
            写入 projects.yaml
          </button>
        </div>
        {codexNotice ? <div className="notice-box">{codexNotice}</div> : null}
        {applyNotice ? <div className="notice-box">{applyNotice}</div> : null}
        {error ? <div className="error-box">{error}</div> : null}
      </div>

      <div className="suggest-layout">
        <div className="panel codex-panel">
          <h3>Codex 终端工作流</h3>
          <p>点击上方“打开 Codex 终端”后，会在 macOS Terminal 启动 Codex。</p>
          <ol className="codex-steps">
            <li>先让 Codex 基于 staging 分析结果给出分类标签草案。</li>
            <li>你和 Codex 聊天确认标签。</li>
            <li>确认后回复“确认标签”，由 Codex 直接写每篇 JSON 的分类结果。</li>
            <li>Codex 会把 Markdown 从“0. 未分类”移动到对应分类目录。</li>
            <li>阶段3直接查看分类后的可视化结果。</li>
          </ol>
        </div>

        <div className="panel suggestion-panel">
          <h3>建议分类（来自 suggest）</h3>
          <ul className="category-list">
            {Object.entries(suggestedCategories).map(([id, name]) => (
              <li key={id}>
                <span className="category-id">{id}</span>
                <span>{name}</span>
              </li>
            ))}
          </ul>

          <h4>建议分类样本</h4>
          <div className="table-box">
            <table>
              <thead>
                <tr>
                  <th>文件</th>
                  <th>建议类别</th>
                  <th>理由</th>
                </tr>
              </thead>
              <tbody>
                {paperClassifications.slice(0, 16).map((item) => (
                  <tr key={`${item.id}-${item.source_pdf}`}>
                    <td>{item.source_pdf}</td>
                    <td>{item.suggested_category}</td>
                    <td>{item.reasoning || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel draft-panel">
          <div className="draft-header">
            <h3>最终分类草案</h3>
            <button className="secondary-btn" onClick={addCategory}>
              新增类别
            </button>
          </div>
          <ul className="draft-list">
            {Object.entries(draft).map(([id, name]) => (
              <li key={id}>
                <span className="category-id">{id}</span>
                <input
                  value={name}
                  onChange={(e) => updateCategoryLabel(id, e.target.value)}
                />
                <button className="danger-btn" onClick={() => removeCategory(id)}>
                  删除
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
