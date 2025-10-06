#!/usr/bin/env python3
"""Create a simple icon for Push-to-Write"""
from PIL import Image, ImageDraw

# Create icon
size = 256
image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)

# Background circle
draw.ellipse([10, 10, size-10, size-10], fill=(70, 130, 180), outline=(50, 90, 140), width=4)

# Microphone shape
mic_width = 60
mic_height = 100
mic_x = (size - mic_width) // 2
mic_y = 50

# Mic body (capsule shape)
draw.ellipse([mic_x, mic_y, mic_x + mic_width, mic_y + mic_height],
             fill=(255, 255, 255), outline=(60, 60, 60), width=3)

# Mic grille lines
for i in range(3):
    y = mic_y + 20 + i * 20
    draw.line([(mic_x + 10, y), (mic_x + mic_width - 10, y)],
              fill=(60, 60, 60), width=2)

# Mic stand
stand_width = 20
stand_x = (size - stand_width) // 2
draw.rectangle([stand_x, mic_y + mic_height - 5, stand_x + stand_width, size - 80],
               fill=(60, 60, 60))

# Mic base
base_width = 80
base_x = (size - base_width) // 2
draw.ellipse([base_x, size - 90, base_x + base_width, size - 50],
             fill=(60, 60, 60))

# Save icon
image.save('icon.png')
print("Icon created: icon.png")