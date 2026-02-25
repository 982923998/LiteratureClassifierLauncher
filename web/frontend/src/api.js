export async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  return response.json();
}

export function wsURL(path) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${protocol}://${window.location.host}${path}`;
}

export function formatTimestamp(ts) {
  if (!ts) {
    return '-';
  }
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) {
    return ts;
  }
  return date.toLocaleString();
}
