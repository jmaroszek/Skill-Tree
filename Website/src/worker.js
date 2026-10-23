export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname === 'www.theskilltree.app' || url.protocol === 'http:') {
      url.hostname = 'theskilltree.app';
      url.protocol = 'https:';
      url.port = '';
      return Response.redirect(url.toString(), 301);
    }
    return env.ASSETS.fetch(request);
  },
};
