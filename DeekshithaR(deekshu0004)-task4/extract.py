import pytesseract
from PIL import Image
import requests
from io import BytesIO 
import cv2 
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
image=Image.open("Output\page_1.png")
print(image)
print(pytesseract.image_to_string(image,lang='eng'))
!wget https://raw.githubusercontent.com/BigPino67/Tesseract-MICR-OCR/master/Tessdata/mcr.traineddata