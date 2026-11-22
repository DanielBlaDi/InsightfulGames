// Test the fixed escapeHtml
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

const test = '<script>alert(1)</script>';
const result = escapeHtml(test);
console.log('Input:', test);
console.log('Output:', result);
console.log('Output (raw):', JSON.stringify(result));
console.log('Includes <script>:', result.includes('<script>'));
console.log('Includes <:', result.includes('<'));
console.log('Includes >:', result.includes('>'));