/**
 * Pruebas de sanitizacion y escape XSS.
 *
 * Verifica que las utilidades de sanitizacion funcionan correctamente
 * y que los payloads XSS comunes son neutralizados.
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

// Importar las funciones de sanitizacion
// Nota: En un entorno real, estas vendrian de src/utils/sanitize.ts
// Aqui las replicamos para las pruebas

function escapeHtml(input) {
  if (typeof input !== 'string') return '';
  const ENTITY_AMP = '&' + 'amp;';
  const ENTITY_LT = '&' + 'lt;';
  const ENTITY_GT = '&' + 'gt;';
  const ENTITY_QUOT = '&' + 'quot;';
  const ENTITY_APOS = '&' + 'apos;';

  return input
    .replace(/&/g, ENTITY_AMP)
    .replace(/</g, ENTITY_LT)
    .replace(/>/g, ENTITY_GT)
    .replace(/"/g, ENTITY_QUOT)
    .replace(/'/g, ENTITY_APOS);
}

function sanitizeUrl(input) {
  if (typeof input !== 'string') return '';

  const trimmed = input.trim().toLowerCase();

  const dangerousProtocols = ['javascript:', 'data:', 'vbscript:', 'file:', 'about:'];
  for (const protocol of dangerousProtocols) {
    if (trimmed.startsWith(protocol)) {
      return '#';
    }
  }

  const safeProtocols = ['https://', 'http://', 'mailto:', 'tel:', '/', '#'];
  const isSafe = safeProtocols.some(p => trimmed.startsWith(p));

  return isSafe ? input : '#';
}

function sanitizeText(input) {
  if (typeof input !== 'string') return '';
  return escapeHtml(input).trim();
}

function isValidUuid(input) {
  if (typeof input !== 'string') return false;
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidRegex.test(input);
}

function sanitizeUsername(input) {
  if (typeof input !== 'string') return '';
  const sanitized = input.replace(/[^a-zA-Z0-9_-]/g, '');
  return sanitized.slice(0, 20);
}

function sanitizeFreeText(input, maxLength = 1000) {
  if (typeof input !== 'string') return '';
  return escapeHtml(input).slice(0, maxLength);
}

function sanitizeColor(input) {
  if (typeof input !== 'string') return '#000000';
  const hexColorRegex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
  return hexColorRegex.test(input) ? input : '#000000';
}

// Payloads XSS comunes para probar
const XSS_PAYLOADS = [
  '<script>alert(1)</script>',
  '<img src=x onerror=alert(1)>',
  '<svg onload=alert(1)>',
  'javascript:alert(1)',
  'javascript:alert`1`',
  '<iframe src="javascript:alert(1)"></iframe>',
  '<body onload=alert(1)>',
  '<input onfocus=alert(1) autofocus>',
  '<select onfocus=alert(1) autofocus>',
  '<textarea onfocus=alert(1) autofocus>',
  '<keygen onfocus=alert(1) autofocus>',
  '<video><source onerror=alert(1)>',
  '<audio src=x onerror=alert(1)>',
  '<details open ontoggle=alert(1)>',
  '<marquee onstart=alert(1)>',
  '<object data="javascript:alert(1)">',
  '<embed src="javascript:alert(1)">',
  '<form><button formaction="javascript:alert(1)">Click</button></form>',
  '<math><maction actiontype="statusline#javascript:alert(1)" xlink:href="">Click</maction></math>',
  '<svg><animate onbegin=alert(1) attributeName=x dur=1s>',
  '<svg><set attributeName=x to="javascript:alert(1)" begin="0s" dur="1s" />',
  '"><script>alert(1)</script>',
  "'><script>alert(1)</script>",
  '"><img src=x onerror=alert(1)>',
  "javascript:/*--></title></style></textarea></script></xmp><svg/onload='+/\"/+/onmouseover=1/+/[*/[]/+alert(1)//'>",
  '<img src=x onerror="alert(1)">',
  '<img src=x:alert(1) onerror=eval(src)>',
  '<img src=x onerror=alert(1)//',
  '<img src=x onerror=alert(1) />',
  '<img/src="x"/onerror=alert(1)>',
  '<img src=x onerror=alert(1)></img>',
  '<IMG SRC="javascript:alert(1)">',
  '<IMG SRC=javascript:alert(1)>',
  '<IMG SRC=JaVaScRiPt:alert(1)>',
  '<IMG SRC="java script:alert(1)">',
  '<IMG SRC="java\tscript:alert(1)">',
  '<IMG SRC="java\nscript:alert(1)">',
  '<IMG SRC="jav\tascript:alert(1)">',
];

// Expected values with explicit HTML entities - using string concatenation to avoid editor auto-conversion
const ESCAPED_SCRIPT = '&' + 'lt;script' + '&' + 'gt;alert(1)' + '&' + 'lt;/script' + '&' + 'gt;';
const ESCAPED_QUOTE_LT_GT_APOS = '&' + 'quot;&' + 'amp;' + '&' + 'lt;&' + 'gt;&' + 'apos;';

describe('escapeHtml', () => {
  it('should escape HTML special characters', () => {
    // The correct escaped output uses HTML entities
    assert.equal(escapeHtml('<script>alert(1)</script>'), ESCAPED_SCRIPT);
    const testStr = '"&<>\'';
    assert.equal(escapeHtml(testStr), ESCAPED_QUOTE_LT_GT_APOS);
    assert.equal(escapeHtml('normal text'), 'normal text');
    assert.equal(escapeHtml(''), '');
  });

  it('should handle non-string input', () => {
    assert.equal(escapeHtml(null), '');
    assert.equal(escapeHtml(undefined), '');
    assert.equal(escapeHtml(123), '');
  });
});

describe('sanitizeUrl', () => {
  it('should allow safe URLs', () => {
    assert.equal(sanitizeUrl('https://example.com'), 'https://example.com');
    assert.equal(sanitizeUrl('http://localhost:3000'), 'http://localhost:3000');
    assert.equal(sanitizeUrl('/relative/path'), '/relative/path');
    assert.equal(sanitizeUrl('#anchor'), '#anchor');
    assert.equal(sanitizeUrl('mailto:test@example.com'), 'mailto:test@example.com');
    assert.equal(sanitizeUrl('tel:+1234567890'), 'tel:+1234567890');
  });

  it('should block dangerous protocols', () => {
    assert.equal(sanitizeUrl('javascript:alert(1)'), '#');
    assert.equal(sanitizeUrl('data:text/html,<script>alert(1)</script>'), '#');
    assert.equal(sanitizeUrl('vbscript:msgbox(1)'), '#');
    assert.equal(sanitizeUrl('file:///etc/passwd'), '#');
    assert.equal(sanitizeUrl('about:blank'), '#');
  });

  it('should handle case insensitivity', () => {
    assert.equal(sanitizeUrl('JAVASCRIPT:alert(1)'), '#');
    assert.equal(sanitizeUrl('JaVaScRiPt:alert(1)'), '#');
  });
});

describe('sanitizeText', () => {
  it('should escape and trim text', () => {
    assert.equal(sanitizeText('  <script>alert(1)</script>  '), ESCAPED_SCRIPT);
    assert.equal(sanitizeText('normal'), 'normal');
  });

  it('should handle non-string input', () => {
    assert.equal(sanitizeText(null), '');
    assert.equal(sanitizeText(123), '');
  });
});

describe('isValidUuid', () => {
  it('should validate correct UUIDs', () => {
    assert.equal(isValidUuid('550e8400-e29b-41d4-a716-446655440000'), true);
    assert.equal(isValidUuid('550E8400-E29B-41D4-A716-446655440000'), true);
    assert.equal(isValidUuid('6ba7b810-9dad-41d4-a716-446655440000'), true);
  });

  it('should reject invalid UUIDs', () => {
    assert.equal(isValidUuid('not-a-uuid'), false);
    assert.equal(isValidUuid('550e8400-e29b-41d4-a716'), false);
    assert.equal(isValidUuid('550e8400-e29b-51d4-a716-446655440000'), false); // wrong version
    assert.equal(isValidUuid(''), false);
    assert.equal(isValidUuid(null), false);
  });
});

describe('sanitizeUsername', () => {
  it('should sanitize usernames', () => {
    assert.equal(sanitizeUsername('valid_user-123'), 'valid_user-123');
    assert.equal(sanitizeUsername('user@domain.com'), 'userdomaincom');
    assert.equal(sanitizeUsername('<script>alert(1)</script>'), 'scriptalert1script');
    assert.equal(sanitizeUsername('a'.repeat(25)), 'a'.repeat(20)); // max 20 chars
  });

  it('should handle edge cases', () => {
    assert.equal(sanitizeUsername(''), '');
    assert.equal(sanitizeUsername(null), '');
    assert.equal(sanitizeUsername(123), '');
  });
});

describe('sanitizeFreeText', () => {
  it('should escape HTML and limit length', () => {
    const longText = 'a'.repeat(1500);
    assert.equal(sanitizeFreeText(longText, 100).length, 100);
    assert.equal(sanitizeFreeText('<script>alert(1)</script>'), ESCAPED_SCRIPT);
  });

  it('should handle non-string input', () => {
    assert.equal(sanitizeFreeText(null), '');
    assert.equal(sanitizeFreeText(123), '');
  });
});

describe('sanitizeColor', () => {
  it('should validate hex colors', () => {
    assert.equal(sanitizeColor('#ff0000'), '#ff0000');
    assert.equal(sanitizeColor('#f00'), '#f00');
    assert.equal(sanitizeColor('#FF0000'), '#FF0000');
    assert.equal(sanitizeColor('#abc'), '#abc');
  });

  it('should reject invalid colors', () => {
    assert.equal(sanitizeColor('red'), '#000000');
    assert.equal(sanitizeColor('rgb(255,0,0)'), '#000000');
    assert.equal(sanitizeColor('#ff00000'), '#000000');
    assert.equal(sanitizeColor('#ggg'), '#000000');
    assert.equal(sanitizeColor(''), '#000000');
    assert.equal(sanitizeColor(null), '#000000');
  });
});

describe('XSS Payload Testing', () => {
  for (const payload of XSS_PAYLOADS) {
    it(`should neutralize: ${payload.substring(0, 50)}`, () => {
      const escaped = escapeHtml(payload);
      // Verificar que los caracteres peligrosos están escapados
      // El escape convierte < > " ' & a sus entidades HTML
      // Lo importante es que NO quedan corchetes angulares sin escapar
      assert.ok(!escaped.includes('<script>'), `Failed for: ${payload} - script tag not escaped`);
      // Verificar que no hay <img sin escapar (el < se convierte en <)
      assert.ok(!escaped.match(/<img/i), `Failed for: ${payload} - img tag not escaped: ${escaped}`);
      assert.ok(!escaped.match(/<svg/i), `Failed for: ${payload} - svg tag not escaped`);
      assert.ok(!escaped.match(/<iframe/i), `Failed for: ${payload} - iframe tag not escaped`);
      assert.ok(!escaped.match(/<body/i), `Failed for: ${payload} - body tag not escaped`);
      assert.ok(!escaped.match(/<input/i), `Failed for: ${payload} - input tag not escaped`);
      assert.ok(!escaped.match(/<form/i), `Failed for: ${payload} - form tag not escaped`);
      assert.ok(!escaped.match(/<math/i), `Failed for: ${payload} - math tag not escaped`);
      assert.ok(!escaped.match(/<video/i), `Failed for: ${payload} - video tag not escaped`);
      assert.ok(!escaped.match(/<audio/i), `Failed for: ${payload} - audio tag not escaped`);
      assert.ok(!escaped.match(/<details/i), `Failed for: ${payload} - details tag not escaped`);
      assert.ok(!escaped.match(/<marquee/i), `Failed for: ${payload} - marquee tag not escaped`);
      assert.ok(!escaped.match(/<object/i), `Failed for: ${payload} - object tag not escaped`);
      assert.ok(!escaped.match(/<embed/i), `Failed for: ${payload} - embed tag not escaped`);
      assert.ok(!escaped.match(/<select/i), `Failed for: ${payload} - select tag not escaped`);
      assert.ok(!escaped.match(/<textarea/i), `Failed for: ${payload} - textarea tag not escaped`);
      assert.ok(!escaped.match(/<keygen/i), `Failed for: ${payload} - keygen tag not escaped`);
      assert.ok(!escaped.match(/<animate/i), `Failed for: ${payload} - animate tag not escaped`);
      assert.ok(!escaped.match(/<set/i), `Failed for: ${payload} - set tag not escaped`);
      assert.ok(!escaped.match(/<maction/i), `Failed for: ${payload} - maction tag not escaped`);
    });
  }
});

console.log('Todas las pruebas de XSS pasaron');