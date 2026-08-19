// support.js — reference helpers for dc-runtime-style templates.
// In the Figma-export preview, .dc.html pages use this to parse
// their own inline <x-dc> template + <script data-dc-script>.
// The production dashboard uses dashboard.js for interactivity,
// so this file is included only on the States reference page.

(function (root) {
  'use strict';

  function getReact() {
    var R = root.React;
    if (!R) throw new Error('dc-runtime: window.React is not available yet');
    return R;
  }

  function getReactDOM() {
    var RD = root.ReactDOM;
    if (!RD) throw new Error('dc-runtime: window.ReactDOM is not available yet');
    return RD;
  }

  var h = function () {
    return getReact().createElement.apply(getReact(), arguments);
  };

  function parseDcDocument(doc) {
    var dc = doc.querySelector('x-dc');
    if (!dc) return null;
    var scriptEl = doc.querySelector('script[data-dc-script]');
    var scriptText = scriptEl ? (scriptEl.textContent || '') : '';
    var propsAttr = scriptEl ? scriptEl.getAttribute('data-props') : null;
    var props = parseDataProps(propsAttr);
    return {
      template: dc.innerHTML,
      js: scriptText,
      props: props.props,
      preview: props.preview
    };
  }

  function parseDcText(src) {
    var openMatch = /<x-dc(?:[\s>][^>]*)?>/.exec(src);
    if (!openMatch) return null;
    var close = src.lastIndexOf('</x-dc>');
    if (close === -1 || close < openMatch.index) return null;
    var template = src.slice(openMatch.index + openMatch[0].length, close);
    var doc = new DOMParser().parseFromString(src, 'text/html');
    var scriptEl = doc.querySelector('script[data-dc-script]');
    var scriptText = scriptEl ? (scriptEl.textContent || '') : '';
    var propsAttr = scriptEl ? scriptEl.getAttribute('data-props') : null;
    var props = parseDataProps(propsAttr);
    return {
      template: template,
      js: scriptText,
      props: props.props,
      preview: props.preview
    };
  }

  function parseDataProps(jsonOrNull) {
    if (!jsonOrNull) return { props: {}, preview: null };
    try {
      var obj = JSON.parse(jsonOrNull);
      return {
        props: obj.props || {},
        preview: obj.preview || null
      };
    } catch (e) {
      return { props: {}, preview: null };
    }
  }

  root.dc = {
    getReact: getReact,
    getReactDOM: getReactDOM,
    h: h,
    parseDocument: parseDcDocument,
    parseText: parseDcText
  };
})(typeof window !== 'undefined' ? window : this);
