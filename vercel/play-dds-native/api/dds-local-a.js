'use strict';
const handler = require('./dds');
module.exports = async function localLaneA(req, res) {
  const origin = String(req && req.headers && req.headers.origin || '');
  const local = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
  if (!local) return handler(req, res);
  const originalSetHeader = res.setHeader.bind(res);
  const originalOrigin = req.headers.origin;
  req.headers.origin = 'https://capgui13.github.io';
  res.setHeader = function(name, value) {
    if (String(name).toLowerCase() === 'access-control-allow-origin') return originalSetHeader(name, originalOrigin);
    return originalSetHeader(name, value);
  };
  try { return await handler(req, res); }
  finally { req.headers.origin = originalOrigin; res.setHeader = originalSetHeader; }
};
