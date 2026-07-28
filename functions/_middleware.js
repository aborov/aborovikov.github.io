export async function onRequest(context) {
  const url = new URL(context.request.url);
  const hostname = url.hostname.toLowerCase();
  const pathname = url.pathname;

  // 1. WWW Subdomain Normalization (www.aborovikov.com -> 301 -> aborovikov.com)
  if (hostname === 'www.aborovikov.com' || hostname.endsWith('.www.aborovikov.com')) {
    url.hostname = 'aborovikov.com';
    url.protocol = 'https:';
    return Response.redirect(url.toString(), 301);
  }

  // 2. Bare Domain Subfolder to Subdomain 301 Redirects
  if (hostname === 'aborovikov.com') {
    if (pathname === '/film' || pathname.startsWith('/film/')) {
      const rest = pathname.replace(/^\/film/, '') || '/';
      return Response.redirect(`https://film.aborovikov.com${rest}${url.search}`, 301);
    }
    if (pathname === '/dev' || pathname.startsWith('/dev/')) {
      const rest = pathname.replace(/^\/dev/, '') || '/';
      return Response.redirect(`https://dev.aborovikov.com${rest}${url.search}`, 301);
    }
    if (pathname === '/brother' || pathname.startsWith('/brother/')) {
      const rest = pathname.replace(/^\/brother/, '') || '/';
      return Response.redirect(`https://brother.aborovikov.com${rest}${url.search}`, 301);
    }
  }

  // 3. Subdomain Redundant Path Cleanup
  if (hostname === 'film.aborovikov.com' || hostname.endsWith('.film.aborovikov.com')) {
    if (pathname === '/film' || pathname.startsWith('/film/')) {
      const rest = pathname.replace(/^\/film/, '') || '/';
      return Response.redirect(`https://film.aborovikov.com${rest}${url.search}`, 301);
    }
  } else if (hostname === 'dev.aborovikov.com' || hostname.endsWith('.dev.aborovikov.com')) {
    if (pathname === '/dev' || pathname.startsWith('/dev/')) {
      const rest = pathname.replace(/^\/dev/, '') || '/';
      return Response.redirect(`https://dev.aborovikov.com${rest}${url.search}`, 301);
    }
  } else if (hostname === 'brother.aborovikov.com' || hostname.endsWith('.brother.aborovikov.com')) {
    if (pathname === '/brother' || pathname.startsWith('/brother/')) {
      const rest = pathname.replace(/^\/brother/, '') || '/';
      return Response.redirect(`https://brother.aborovikov.com${rest}${url.search}`, 301);
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
    return Response.redirect(url.toString(), 301);
  }

  // 5. Bypass Subdomain Routing for Restored Dedicated Subpages (/ccc/, /musician/, /musician-ru/)
  if (
    pathname.startsWith('/ccc/') ||
    pathname.startsWith('/musician/') ||
    pathname.startsWith('/musician-ru/')
  ) {
    return context.next();
  }

  // 6. Subdomain Internal Serving (e.g. film.aborovikov.com/ -> serves /film/ internally)
  if (hostname === 'film.aborovikov.com' || hostname.endsWith('.film.aborovikov.com')) {
    if (!isAssetRequest) {
      url.pathname = `/film${pathname}`;
      return fetch(new Request(url.toString(), context.request));
    }
  } else if (hostname === 'dev.aborovikov.com' || hostname.endsWith('.dev.aborovikov.com')) {
    if (!isAssetRequest) {
      url.pathname = `/dev${pathname}`;
      return fetch(new Request(url.toString(), context.request));
    }
  } else if (hostname === 'brother.aborovikov.com' || hostname.endsWith('.brother.aborovikov.com')) {
    if (!isAssetRequest) {
      url.pathname = `/brother${pathname}`;
      return fetch(new Request(url.toString(), context.request));
    }
  }

  // 7. Default Routing (aborovikov.com -> root static files)
  return context.next();
}
