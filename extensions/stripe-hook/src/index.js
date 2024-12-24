// extensions/hooks/stripe-webhook-middleware/index.js
const express = require('express');

module.exports = function registerHook({ init }) {
  init('middlewares.before', async function ({ app }) {
    app.use(
      express.json({
        verify: (req, res, buf) => {
          if (req.originalUrl.startsWith('/stripe')) {
            req.rawBody = buf.toString();
          }
        }
      })
    );
  });
};
