'use strict';
const handler = require('./dds');
module.exports = async function fileLaneB(req, res) {
  const origin = String(req && req.headers && req.headers.origin || '');
  if (origin !== 'null') return handler(req, res);
  const originalSetHeader = res.setHeader.bind(res);
  const originalOrigin = req.headers.origin;
  req.headers.origin = 'https://capgui13.github.io';
  res.setHeader = function(name, value) {
    if (String(name).toLowerCase() === 'access-control-allow-origin') return originalSetHeader(name, 'null');
    return originalSetHeader(name, value);
  };
  try { return await handler(req, res); }
  finally { req.headers.origin = originalOrigin; res.setHeader = originalSetHeader; }
};
