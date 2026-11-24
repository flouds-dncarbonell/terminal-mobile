// Local 9router Claude usage fix. Dependencies k (fetch) and i (cache) belong
// to the existing usage module; reset-credit requests invalidate the same i.
async function j(token, proxy = null, options = {}) {
  if (!token) return {message: 'No Claude access token available.', usageStale: true};
  let entry = i.get(token);
  if (!entry) {
    entry = {result: null, fetchedAt: 0, lastAttemptAt: 0, retryAt: 0, failures: 0};
    i.set(token, entry);
  }
  const snapshot = () => ({
    ...(entry.result || {}),
    usageFetchedAt: entry.fetchedAt ? new Date(entry.fetchedAt).toISOString() : null,
    usageStale: !entry.result || Boolean(entry.error),
    usageRetryAt: entry.retryAt ? new Date(entry.retryAt).toISOString() : null,
    ...(entry.error ? {usageError: entry.error, message: entry.error.message} : {}),
  });
  // Forced refreshes share in-flight work and cannot override provider backoff.
  if (entry.promise) return entry.promise;
  const now = Date.now();
  if (entry.retryAt > now) return snapshot();
  if (entry.result && (now - entry.lastAttemptAt < 60000 ||
      (options?.force !== true && now - entry.fetchedAt < 300000))) return snapshot();
  entry.promise = Promise.resolve().then(async () => {
    entry.lastAttemptAt = Date.now();
    try {
      const result = await k(token, proxy);
      if (!result?.quotas || Object.keys(result.quotas).length === 0) {
        throw Object.assign(new Error('Claude returned no quota data.'), {status: 200});
      }
      entry.result = result;
      entry.fetchedAt = Date.now();
      entry.failures = 0;
      entry.retryAt = 0;
      entry.error = null;
    } catch (error) {
      const status = Number.isInteger(error?.status) ? error.status : null;
      const limited = status === 429;
      const authentication = status === 401 || status === 403;
      entry.failures = (entry.failures || 0) + 1;
      const delay = Math.min(1800000, (limited ? 300000 : 60000) *
        2 ** Math.min(entry.failures - 1, 5));
      entry.retryAt = Date.now() + Math.max(delay, error?.retryAfterMs || 0);
      entry.error = {
        code: limited ? 'rate_limited' : authentication ? 'authentication_error' : 'usage_unavailable',
        status,
        message: limited
          ? 'Claude usage is temporarily rate limited (HTTP 429). Waiting before retrying.'
          : authentication
            ? `Claude usage authorization failed (HTTP ${status}, ${status === 401 ? 'unauthorized' : 'forbidden'}).`
            : `Claude usage is temporarily unavailable${status ? ` (HTTP ${status})` : ''}. Waiting before retrying.`,
      };
      console.warn(`[Claude Usage] ${entry.error.code}${status ? ` (HTTP ${status})` : ''}; retry at ${new Date(entry.retryAt).toISOString()}`);
    } finally {
      // Never leave a settled promise cached indefinitely after a failure.
      entry.promise = null;
    }
    return snapshot();
  });
  return entry.promise;
}
