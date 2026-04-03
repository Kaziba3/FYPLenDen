import os
import re

regex = re.compile(r'({{[^}]*?\n[^}]*?}}|{%[^%]*?\n[^%]*?%})', re.DOTALL)

def fix_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_content = regex.sub(lambda m: m.group(0).replace('\n', ' ').replace('  ', ' '), content)
        
        if content != new_content:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            return True
    except Exception as e:
        print(f"Error processing {path}: {e}")
    return False

count = 0
for r, ds, fs in os.walk('templates'):
    for f in fs:
        if f.endswith('.html'):
            if fix_file(os.path.join(r, f)):
                count += 1

print(f"Successfully processed {count} templates")
