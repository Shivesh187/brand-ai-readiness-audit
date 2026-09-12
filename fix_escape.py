with open(r'C:\Users\sunil\OneDrive\Desktop\Projects\Adobe\brand-ai-readiness-audit\web\app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the escapeHtml function
idx = content.find('function escapeHtml(str)')
if idx >= 0:
    # Find the end of the function (next function or end of file)
    end_idx = content.find('\nfunction ', idx + 1)
    if end_idx < 0:
        end_idx = len(content)
    else:
        # Include the newline before the next function
        end_idx += 1
    
    old_func = content[idx:end_idx]
    print('Found function:', repr(old_func[:300]))
    
    # Replace with correct version using proper HTML entities
    new_func = """function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&')
        .replace(/</g, '<')
        .replace(/>/g, '>')
        .replace(/"/g, '"')
        .replace(/'/g, '&#039;');
}
"""
    content = content[:idx] + new_func + content[idx + len(old_func):]
    with open(r'C:\Users\sunil\OneDrive\Desktop\Projects\Adobe\brand-ai-readiness-audit\web\app.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed!')
else:
    print('Function not found')