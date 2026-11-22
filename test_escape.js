function escapeHtml(input) {
  if (typeof input !== 'string') return '';
  return input
    .replace(/&/g, '&')
    .replace(/</g, '<')
    .replace(/>/g, '>')
    .replace(/"/g, '"')
    .replace(/'/g, '&apos;');
}

const test = '<script>alert(1)</script>';
const result = escapeHtml(test);
console.log('Input:', test);
console.log('Output:', result);
console.log('Output (raw):', JSON.stringify(result));
console.log('Includes <script>:', result.includes('<script>'));
console.log('Includes <script>:', result.includes('<script>'));
console.log('---');
console.log('Contains literal < character:', result.includes('<'));
console.log('Contains literal > character:', result.includes('>'));
console.log('Contains <:', result.includes('<'));
console.log('Contains >:', result.includes('>'));