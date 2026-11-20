import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Runs an async loader and exposes loading, error, and data state.
 * `reload` re-runs the loader. Responses from superseded requests are ignored.
 */
export function useAsync(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [version, setVersion] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    const token = ++latest.current;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    loader()
      .then((data) => {
        if (token === latest.current) setState({ data, error: null, loading: false });
      })
      .catch((error) => {
        if (token === latest.current) setState({ data: null, error, loading: false });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { ...state, reload };
}
