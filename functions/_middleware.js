export async function onRequest(context) {
  const url = new URL(context.request.url);
  const hostname = url.hostname.toLowerCase();

  // Bypass subdomain routing for restored dedicated subpages (/ccc/, /musician/, /musician-ru/)
  if (
    url.pathname === '/ccc' || url.pathname.startsWith('/ccc/') ||
    url.pathname === '/musician' || url.pathname.startsWith('/musician/') ||
    url.pathname === '/musician-ru' || url.pathname.startsWith('/musician-ru/')
  ) {
    return context.next();
  }

  // If requesting assets (images, css, js) from a subdomain, check if they exist under the subdomain folder or fall back to root assets
  const isAssetRequest = 
    url.pathname.startsWith('/css/') || 
    url.pathname.startsWith('/js/') || 
    url.pathname.startsWith('/images/') ||
    url.pathname.includes('.');

  // 1. Route film.aborovikov.com -> /film
  if (hostname === 'film.aborovikov.com' || hostname.endsWith('.film.aborovikov.com')) {
    if (!url.pathname.startsWith('/film')) {
      if (!isAssetRequest || url.pathname.startsWith('/film/')) {
        url.pathname = `/film${url.pathname}`;
        return fetch(new Request(url.toString(), context.request));
      }
    }
  }

  // 2. Route dev.aborovikov.com -> /dev
  else if (hostname === 'dev.aborovikov.com' || hostname.endsWith('.dev.aborovikov.com')) {
    if (!url.pathname.startsWith('/dev')) {
      if (!isAssetRequest || url.pathname.startsWith('/dev/')) {
        url.pathname = `/dev${url.pathname}`;
        return fetch(new Request(url.toString(), context.request));
      }
    }
  }

  // 3. Route brother.aborovikov.com -> /brother
  else if (hostname === 'brother.aborovikov.com' || hostname.endsWith('.brother.aborovikov.com')) {
    if (!url.pathname.startsWith('/brother')) {
      if (!isAssetRequest || url.pathname.startsWith('/brother/')) {
        url.pathname = `/brother${url.pathname}`;
        return fetch(new Request(url.toString(), context.request));
      }
    }
  }

  // Otherwise, route normally (aborovikov.com -> root of project)
  return context.next();
}
