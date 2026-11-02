// Helper to ensure HSTS header is present on all responses (200s and 301 redirects)
function withSecurityHeaders(response) {
  const newHeaders = new Headers(response.headers);
  newHeaders.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders
  });
}

function redirect301(targetUrl) {
  return new Response(null, {
    status: 301,
    headers: {
      'Location': targetUrl,
      'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
    }
  });
}

export async function onRequest(context) {
  // If this is an internal rewrite fetch, bypass middleware redirect rules and serve static content
  if (context.request.headers.get('x-internal-rewrite') === '1') {
    return context.next();
  }

  const url = new URL(context.request.url);
  const hostname = url.hostname.toLowerCase();
  const pathname = url.pathname;

  // Helper to make internal fetch subrequests without triggering redirect loops
  async function fetchInternal(targetPath) {
    const targetUrl = new URL(context.request.url);
    targetUrl.pathname = targetPath;
    const reqHeaders = new Headers(context.request.headers);
    reqHeaders.set('x-internal-rewrite', '1');
    const internalReq = new Request(targetUrl.toString(), {
      method: context.request.method,
      headers: reqHeaders,
      body: context.request.body,
      redirect: 'manual'
    });
    const res = await fetch(internalReq);
    return withSecurityHeaders(res);
  }

  // 1. WWW Subdomain Normalization (www.aborovikov.com -> 301 -> aborovikov.com)
  if (hostname === 'www.aborovikov.com' || hostname.endsWith('.www.aborovikov.com') || hostname.startsWith('www.')) {
    return redirect301(`https://aborovikov.com${pathname}${url.search}`);
  }

  // 1b. Legacy URL 301 Redirects (eliminate 404s for all retired historical routes)
  if (pathname === '/bs' || pathname.startsWith('/bs/') || pathname === '/bs-ru' || pathname.startsWith('/bs-ru/')) {
    return redirect301(`https://brother.aborovikov.com/`);
  }
  if (pathname === '/ru' || pathname.startsWith('/ru/')) {
    return redirect301(`https://aborovikov.com/musician-ru/`);
  }
  if (
    pathname === '/commercial' || pathname.startsWith('/commercial/') ||
    pathname === '/portfolio' || pathname.startsWith('/portfolio/') ||
    pathname === '/post' || pathname.startsWith('/post/')
  ) {
    return redirect301(`https://film.aborovikov.com/`);
  }
  if (pathname === '/en' || pathname.startsWith('/en/')) {
    return redirect301(`https://aborovikov.com/`);
  }

  // 2. Bare Domain Subfolder to Subdomain 301 Redirects
  if (hostname === 'aborovikov.com') {
    if (pathname === '/film' || pathname.startsWith('/film/')) {
      const rest = pathname.replace(/^\/film/, '') || '/';
      return redirect301(`https://film.aborovikov.com${rest}${url.search}`);
    }
    if (pathname === '/dev' || pathname.startsWith('/dev/')) {
      const rest = pathname.replace(/^\/dev/, '') || '/';
      return redirect301(`https://dev.aborovikov.com${rest}${url.search}`);
    }
    if (pathname === '/brother' || pathname.startsWith('/brother/')) {
      const rest = pathname.replace(/^\/brother/, '') || '/';
      return redirect301(`https://brother.aborovikov.com${rest}${url.search}`);
    }
  }

  // 3. Subdomain Redundant Path Cleanup (e.g. film.aborovikov.com/film/ -> 301 -> film.aborovikov.com/)
  if (hostname === 'film.aborovikov.com' || hostname.endsWith('.film.aborovikov.com')) {
    if (pathname === '/film' || pathname.startsWith('/film/')) {
      const rest = pathname.replace(/^\/film/, '') || '/';
      return redirect301(`https://film.aborovikov.com${rest}${url.search}`);
    }
  } else if (hostname === 'dev.aborovikov.com' || hostname.endsWith('.dev.aborovikov.com')) {
    if (pathname === '/dev' || pathname.startsWith('/dev/')) {
      const rest = pathname.replace(/^\/dev/, '') || '/';
      return redirect301(`https://dev.aborovikov.com${rest}${url.search}`);
    }
  } else if (hostname === 'brother.aborovikov.com' || hostname.endsWith('.brother.aborovikov.com')) {
    if (pathname === '/brother' || pathname.startsWith('/brother/')) {
      const rest = pathname.replace(/^\/brother/, '') || '/';
      return redirect301(`https://brother.aborovikov.com${rest}${url.search}`);
    }
  }

  const isAssetRequest = 
    pathname.startsWith('/css/') || 
    pathname.startsWith('/js/') || 
    pathname.startsWith('/images/') ||
    pathname.includes('.');

  // 4. Trailing Slash Normalization for Non-Asset Paths (/ccc -> 301 -> /ccc/)
  if (!isAssetRequest && pathname !== '/' && !pathname.endsWith('/')) {
    url.pathname = `${pathname}/`;
    return redirect301(url.toString());
  }

  // 5. Bypass Subdomain Routing for Restored Dedicated Subpages (/ccc/, /musician/, /musician-ru/)
  if (
    pathname.startsWith('/ccc/') ||
    pathname.startsWith('/musician/') ||
    pathname.startsWith('/musician-ru/')
  ) {
    const res = await context.next();
    return withSecurityHeaders(res);
  }

  // 6. Subdomain Internal Serving (e.g. film.aborovikov.com/ -> serves /film/ internally)
  if (hostname === 'film.aborovikov.com' || hostname.endsWith('.film.aborovikov.com')) {
    if (!isAssetRequest) {
      return fetchInternal(`/film${pathname}`);
    }
  } else if (hostname === 'dev.aborovikov.com' || hostname.endsWith('.dev.aborovikov.com')) {
    if (!isAssetRequest) {
      return fetchInternal(`/dev${pathname}`);
    }
  } else if (hostname === 'brother.aborovikov.com' || hostname.endsWith('.brother.aborovikov.com')) {
    if (!isAssetRequest) {
      return fetchInternal(`/brother${pathname}`);
    }
  }

  // 7. Default Routing (aborovikov.com -> root static files)
  const res = await context.next();
  return withSecurityHeaders(res);
}
