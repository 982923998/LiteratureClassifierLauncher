import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { fetchJSON } from '../api';

export default function ClassifyPage() {
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState('');
  const [papers, setPapers] = useState([]);
  const [selectedPdf, setSelectedPdf] = useState('');
  const [markdownContent, setMarkdownContent] = useState('');
  const [error, setError] = useState('');

  const selectedPaper = useMemo(
    () => papers.find((item) => item.source_pdf === selectedPdf) || null,
    [papers, selectedPdf]
  );

  const loadProjects = useCallback(async () => {
    try {
      const data = await fetchJSON('/api/projects');
      setProjects(data.projects || []);
      setProject((prev) => prev || data.projects?.[0]?.id || '');
    } catch (err) {
      setError(String(err.message || err));
    }
  }, []);

  const loadPapers = useCallback(async (projectId) => {
    if (!projectId) {
      return;
    }
    try {
      const data = await fetchJSON(`/api/projects/${projectId}/papers`);
      setPapers(data.papers || []);
      setSelectedPdf((prev) =>
        (data.papers || []).some((item) => item.source_pdf === prev)
          ? prev
          : data.papers?.[0]?.source_pdf || ''
      );
    } catch (err) {
      setError(String(err.message || err));
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (project) {
      loadPapers(project);
    }
  }, [project, loadPapers]);

  useEffect(() => {
    async function loadMarkdown() {
      if (!project || !selectedPaper?.md_path) {
        setMarkdownContent('');
        return;
      }

      const query = new URLSearchParams({
        project,
        path: selectedPaper.md_path
      });

      try {
        const response = await fetch(`/api/md?${query.toString()}`);
        if (!response.ok) {
          throw new Error(await response.text());
        }
        const text = await response.text();
        setMarkdownContent(text);
      } catch (err) {
        setMarkdownContent(`读取 Markdown 失败: ${String(err.message || err)}`);
      }
    }

    loadMarkdown();
  }, [project, selectedPaper?.md_path]);

  const groupedPapers = useMemo(() => {
    const map = {};
    for (const paper of papers) {
      const key = paper.category_name || '0. 未分类';
      if (!map[key]) {
        map[key] = [];
      }
      map[key].push(paper);
    }
    return map;
  }, [papers]);

  return (
    <section className="stage-page">
      <div className="panel control-panel">
        <div className="control-grid classify-control-grid">
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
        </div>

        {error ? <div className="error-box">{error}</div> : null}
      </div>

      <div className="classify-layout">
        <div className="panel grouped-panel">
          <h3>分类结果</h3>
          <div className="grouped-list">
            {Object.entries(groupedPapers).map(([group, items]) => (
              <div key={group} className="group-card">
                <h4>
                  {group} <span>({items.length})</span>
                </h4>
                <ul>
                  {items.map((item) => (
                    <li
                      key={item.source_pdf}
                      className={selectedPdf === item.source_pdf ? 'active' : ''}
                      onClick={() => setSelectedPdf(item.source_pdf)}
                    >
                      {item.title || item.source_pdf}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="panel markdown-panel">
          <h3>文献详情</h3>
          {selectedPaper ? (
            <div className="detail-head">
              <div>{selectedPaper.source_pdf}</div>
              <div>{selectedPaper.category_name || '0. 未分类'}</div>
            </div>
          ) : null}

          {markdownContent ? (
            <article className="markdown-body">
              <ReactMarkdown>{markdownContent}</ReactMarkdown>
            </article>
          ) : (
            <div className="empty-box">当前文献暂无 Markdown</div>
          )}
        </div>
      </div>
    </section>
  );
}
