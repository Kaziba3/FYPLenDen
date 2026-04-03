import os
import re

# Define the root templates directory
templates_dir = r"c:\Users\ARYAN\OneDrive\Desktop\LenDen\templates"

# Mapping of old hex colors/fonts to new variables or Tailwind classes
# Based on the user's provided code:
# --primary-green: #2E7D32
# --dark-green: #1B5E20
# --light-green: #4CAF50
# --lighter-green: #C8E6C9
# --accent-green: #81C784

replacements = {
    # Fonts
    'font-outfit': 'font-sans',
    'Poppins, sans-serif': 'Poppins, sans-serif', # Just to be safe
    'Inter, sans-serif': 'Poppins, sans-serif',
    
    # Direct Hex to Tailwind Primary Classes (using the new config in base.html)
    r'\[#1E7F5C\]': 'primary-600',
    r'#1E7F5C': 'var(--primary-green)',
    
    r'\[#145940\]': 'primary-800',
    r'#145940': 'var(--dark-green)',
    
    r'\[#2ECC71\]': 'primary-500',
    r'#2ECC71': 'var(--light-green)',
    
    r'\[#A7E9C5\]': 'primary-300',
    r'#A7E9C5': 'var(--accent-green)',
    
    r'\[#F6FFF9\]': 'primary-50',
    r'#F6FFF9': 'var(--bg-color)',
}

# Regex to find tailwind utility classes with hex colors like bg-[#1E7F5C]
tw_hex_regex = re.compile(r'(\w+)-\[#([A-Fa-f0-9]{6})\]')

def update_content(content):
    # 1. Replace specific strings
    for old, new in replacements.items():
        if old.startswith(r'['): # Handle escaped brackets in mapping
            content = content.replace(old.replace('\\', ''), new)
        else:
            content = content.replace(old, new)
    
    # 2. Replace arbitrary tailwind hexes that match our known ones
    def tw_replacer(match):
        prefix = match.group(1)
        hex_val = match.group(2).upper()
        
        mapping = {
            '1E7F5C': 'primary-600',
            '145940': 'primary-800',
            '2ECC71': 'primary-500',
            'A7E9C5': 'primary-300',
            'F6FFF9': 'primary-50',
        }
        
        if hex_val in mapping:
            return f"{prefix}-{mapping[hex_val]}"
        return match.group(0)

    content = tw_hex_regex.sub(tw_replacer, content)
    
    # 3. Fix font links in <head> if they exist (for standalone pages)
    content = re.sub(
        r'<link\s+href="https://fonts\.googleapis\.com/css2\?family=Inter[^"]+"[^>]*>',
        '<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">',
        content
    )
    content = re.sub(
        r'<link\s+href="https://fonts\.googleapis\.com/css2\?family=Outfit[^"]+"[^>]*>',
        '<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">',
        content
    )
    
    # 4. Update embedded tailwind config if it exists
    content = re.sub(
        r'tailwind\.config\s*=\s*\{.*?\}',
        """tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Poppins', 'sans-serif'],
                        outfit: ['Poppins', 'sans-serif'],
                    },
                    colors: {
                        primary: {
                            50: '#C8E6C9',
                            100: '#C8E6C9',
                            200: '#81C784', 
                            300: '#81C784',
                            400: '#4CAF50', 
                            500: '#4CAF50', 
                            600: '#2E7D32', 
                            700: '#2E7D32',
                            800: '#1B5E20', 
                            900: '#1B5E20', 
                            950: '#052e16',
                        },
                    }
                }
            }
        }""",
        content,
        flags=re.DOTALL
    )

    return content

def main():
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                # Skip base.html and landing.html as they were manually updated already
                if file in ["base.html", "landing.html"]:
                    continue
                    
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                new_content = update_content(content)
                
                if new_content != content:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"Updated: {path}")

if __name__ == "__main__":
    main()
