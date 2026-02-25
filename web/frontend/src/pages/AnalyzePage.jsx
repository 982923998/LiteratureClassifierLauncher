import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchJSON, formatTimestamp, wsURL } from '../api';

const MAX_LOG_LINES = 1200;

export default function AnalyzePage() {
  const [projects, setProjects] = useState([]);
  const [pdfDir, setPdfDir] = useState('');
  const [papers, setPapers] = useState([]);
  const [selectedPdf, setSelectedPdf] = useState('');

  const [limit, setLimit] = useState('');
  const [single, setSingle] = useState('');
  const [workers, setWorkers] = useState(3);

  const [task, setTask] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState('');

  const wsRef = useRef(null);

  const selectedPaper = useMemo(
    () => papers.find((item) => item.source_pdf === selectedPdf) || null,
    [papers, selectedPdf]
  );

  const loadProjects = useCallback(async () => {
    try {
      const data = await fetchJSON('/api/projects');
      setProjects(data.projects || []);
      setPdfDir((prev) => prev || data.projects?.[0]?.pdf_dir || '');
    } catch (err) {
      setError(String(err.message || err));
    }
  }, []);

  const loadPapers = useCallback(async (pathValue, silent = false) => {
    const trimmed = (pathValue || '').trim();
    if (!trimmed) {
      setPapers([]);
      setSelectedPdf('');
      return;
    }
    try {
      const query = new URLSearchParams({ pdf_dir: trimmed });
      const data = await fetchJSON(`/api/analyze/papers?${query.toString()}`);
      setPapers(data.papers || []);
      setSelectedPdf((prev) =>
        (data.papers || []).some((item) => item.source_pdf === prev)
          ? prev
          : data.papers?.[0]?.source_pdf || ''
      );
    } catch (err) {
      setPapers([]);
      setSelectedPdf('');
      if (!silent) {
        setError(String(err.message || err));
      }
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (pdfDir.trim()) {
      loadPapers(pdfDir, true);
    }
  }, [pdfDir, loadPapers]);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const connectTaskSocket = useCallback(
    (taskId) => {
      if (wsRef.current) {
        wsRef.current.close();
      }

      const socket = new WebSocket(wsURL(`/ws/tasks/${taskId}`));
      wsRef.current = socket;

      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);

        if (payload.type === 'snapshot') {
          setTask(payload.task || null);
          setLogs(payload.logs || []);
          return;
        }

        if (payload.type === 'log') {
          setLogs((prev) => [...prev, payload.line].slice(-MAX_LOG_LINES));
          return;
        }

        if (payload.type === 'status') {
          setTask(payload.task || null);
          if (payload.task?.status === 'success' || payload.task?.status === 'failed') {
            loadPapers(pdfDir);
          }
          return;
        }

        if (payload.type === 'error') {
          setError(payload.message || '任务连接异常');
        }
      };

      socket.onerror = () => {
        setError('任务日志 WebSocket 连接失败');
      };
    },
    [loadPapers, pdfDir]
  );

  const handleStartAnalyze = async () => {
    if (!pdfDir.trim()) {
      setError('请先输入 PDF 路径');
      return;
    }

    setError('');
    setLogs([]);

    const payload = {
      pdf_dir: pdfDir.trim(),
      workers: Number(workers) || 3
    };

    if (single.trim()) {
      payload.single = single.trim();
    } else if (limit.trim()) {
      payload.limit = Number(limit);
    }

    try {
      const result = await fetchJSON('/api/analyze/start', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      setTask(result.task);
      connectTaskSocket(result.task.task_id);
    } catch (err) {
      setError(String(err.message || err));
    }
  };

  const openPdfInNewTab = useCallback(
    async (paper) => {
      if (!paper?.pdf_path || !pdfDir) {
        setError('当前文献没有可用 PDF 路径');
        return;
      }

      try {
        await fetchJSON('/api/pdf/open', {
          method: 'POST',
          body: JSON.stringify({
            pdf_dir: pdfDir,
            path: paper.pdf_path
          })
        });
      } catch (err) {
        setError(String(err.message || err));
      }
    },
    [pdfDir]
  );

  return (
    <section className="stage-page">
      <div className="panel control-panel">
        <div className="control-grid">
          <label>
            PDF 路径
            <input
              value={pdfDir}
              onChange={(e) => setPdfDir(e.target.value)}
              placeholder="输入或粘贴包含 PDF 的目录路径"
              list="pdf-path-presets"
            />
            <datalist id="pdf-path-presets">
              {projects.map((item) => (
                <option key={item.id} value={item.pdf_dir}>
                  {item.name} ({item.id})
                </option>
              ))}
            </datalist>
          </label>
          <label>
            Limit
            <input
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              placeholder="可选，仅前 N 篇"
            />
          </label>
          <label>
            Single
            <input
              value={single}
              onChange={(e) => setSingle(e.target.value)}
              placeholder="可选，单个 PDF 文件名"
            />
          </label>
          <label>
            Workers
            <input
              type="number"
              min={1}
              max={16}
              value={workers}
              onChange={(e) => setWorkers(e.target.value)}
            />
          </label>
          <button className="primary-btn" onClick={handleStartAnalyze}>
            启动 Analyze
          </button>
        </div>

        {task ? (
          <div className="task-status">
            <span>任务: {task.task_id}</span>
            <span className={`status-badge status-${task.status}`}>{task.status}</span>
            <span>开始时间: {formatTimestamp(task.started_at)}</span>
          </div>
        ) : null}

        {error ? <div className="error-box">{error}</div> : null}
      </div>

      <div className="analyze-layout">
        <div className="panel paper-list-panel">
          <h3>文献列表</h3>
          <ul className="paper-list">
            {papers.map((item) => (
              <li
                key={item.source_pdf}
                className={`paper-item ${selectedPdf === item.source_pdf ? 'paper-item-active' : ''}`}
                onClick={() => setSelectedPdf(item.source_pdf)}
              >
                <div className="paper-row">
                  <div className="paper-title">{item.title || item.source_pdf}</div>
                  <button
                    type="button"
                    className="secondary-btn tiny-btn"
                    onClick={(event) => {
                      event.stopPropagation();
                      openPdfInNewTab(item);
                    }}
                  >
                    用 PDF Expert 打开
                  </button>
                </div>
                <div className="paper-file">{item.source_pdf}</div>
              </li>
            ))}
          </ul>
        </div>

        <div className="panel markdown-panel">
          <h3>实时日志</h3>
          <pre className="terminal-log analyze-terminal-log">{logs.join('\n')}</pre>
        </div>
      </div>
    </section>
  );
}
