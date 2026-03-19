import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageFilter, ImageOps
import cv2
import numpy as np
import os
import shutil
from datetime import datetime
import threading
import queue
import json

CONFIG = {
    "app_name": "Image to Painter - Your Photo, Artist's Brush",
    "version": "1.0.0",
    "window_size": "1200x700",
    "min_window_size": "900x600",
    "temp_folder": "temp_uploads",
    "output_folder": "output",
    "config_file": "portraitai_config.json",
    "max_file_size": 10 * 1024 * 1024,
    "supported_formats": [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"]
}

class ArtStyles:
    @staticmethod
    def pencil_sketch(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        inverted = cv2.bitwise_not(gray)
        blurred = cv2.GaussianBlur(inverted, (21, 21), 0)
        sketch = cv2.divide(gray, 255 - blurred, scale=256)
        sketch_bgr = cv2.cvtColor(sketch, cv2.COLOR_GRAY2BGR)
        return sketch_bgr
    
    @staticmethod
    def color_sketch(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        inverted = cv2.bitwise_not(gray)
        blurred = cv2.GaussianBlur(inverted, (21, 21), 0)
        sketch = cv2.divide(gray, 255 - blurred, scale=256)
        sketch_3ch = cv2.cvtColor(sketch, cv2.COLOR_GRAY2BGR)
        blended = cv2.addWeighted(image, 0.3, sketch_3ch, 0.7, 0)
        return blended
    
    @staticmethod
    def cartoon_effect(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 5)
        edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 9)
        color = cv2.bilateralFilter(image, 9, 300, 300)
        cartoon = cv2.bitwise_and(color, color, mask=edges)
        return cartoon
    
    @staticmethod
    def watercolor_effect(image):
        filtered = cv2.bilateralFilter(image, 15, 80, 80)
        kernel = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(filtered, -1, kernel)
        blurred = cv2.GaussianBlur(sharpened, (0, 0), 3)
        watercolor = cv2.addWeighted(sharpened, 1.5, blurred, -0.5, 0)
        return watercolor
    
    @staticmethod
    def oil_painting(image):
        img = image.copy()
        for _ in range(3):
            img = cv2.medianBlur(img, 5)
        kernel = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
        img = cv2.filter2D(img, -1, kernel)
        return img
    
    @staticmethod
    def crayon_effect(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        kernel = np.ones((2,2), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)
        z = image.reshape((-1,3))
        z = np.float32(z)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        k = 8
        _, label, center = cv2.kmeans(z, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        center = np.uint8(center)
        res = center[label.flatten()]
        quantized = res.reshape((image.shape))
        edges_colored = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        crayon = cv2.addWeighted(quantized, 0.8, edges_colored, 0.2, 0)
        return crayon
    
    @staticmethod
    def comic_book(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        edges = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        z = image.reshape((-1,3))
        z = np.float32(z)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        k = 12
        _, label, center = cv2.kmeans(z, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        center = np.uint8(center)
        res = center[label.flatten()]
        quantized = res.reshape((image.shape))
        h, w = quantized.shape[:2]
        if h > 100 and w > 100:
            small = cv2.resize(quantized, (w//4, h//4))
            quantized = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
        comic = cv2.addWeighted(quantized, 0.7, edges, 0.3, 0)
        return comic
    
    @staticmethod
    def pop_art(image):
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hsv[:,:,1] = cv2.add(hsv[:,:,1], 50)
        hsv[:,:,2] = cv2.multiply(hsv[:,:,2], 1.2)
        pop = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        z = pop.reshape((-1,3))
        z = np.float32(z)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        k = 6
        _, label, center = cv2.kmeans(z, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        center = np.uint8(center)
        res = center[label.flatten()]
        pop = res.reshape((pop.shape))
        return pop

class PortraitAI:
    def __init__(self, root):
        self.root = root
        self.root.title(CONFIG["app_name"])
        self.root.geometry(CONFIG["window_size"])
        self.root.minsize(900, 600)
        
        self.current_image = None
        self.original_image = None
        self.processed_image = None
        self.image_path = None
        self.current_style = tk.StringVar(value="pencil_sketch")
        self.processing = False
        self.progress_queue = queue.Queue()
        
        self.styles = {
            "pencil_sketch": {"name": "Pencil Sketch", "func": ArtStyles.pencil_sketch, "icon": "✏️"},
            "color_sketch": {"name": "Color Sketch", "func": ArtStyles.color_sketch, "icon": "🎨"},
            "cartoon": {"name": "Cartoon", "func": ArtStyles.cartoon_effect, "icon": "😊"},
            "watercolor": {"name": "Watercolor", "func": ArtStyles.watercolor_effect, "icon": "💧"},
            "oil_painting": {"name": "Oil Painting", "func": ArtStyles.oil_painting, "icon": "🖼️"},
            "crayon": {"name": "Crayon", "func": ArtStyles.crayon_effect, "icon": "🖍️"},
            "comic": {"name": "Comic Book", "func": ArtStyles.comic_book, "icon": "📚"},
            "pop_art": {"name": "Pop Art", "func": ArtStyles.pop_art, "icon": "🎭"}
        }
        
        os.makedirs(CONFIG["temp_folder"], exist_ok=True)
        os.makedirs(CONFIG["output_folder"], exist_ok=True)
        
        self.load_config()
        self.setup_ui()
        self.setup_drag_drop()
        self.check_progress_queue()
    
    def setup_drag_drop(self):
        self.root.bind("<Enter>", self.on_enter)
        self.root.bind("<Leave>", self.on_leave)
        
    def on_enter(self, event):
        if event.widget == self.root:
            self.root.configure(bg='lightblue')
    
    def on_leave(self, event):
        if event.widget == self.root:
            self.root.configure(bg='SystemButtonFace')
    
    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        left_panel = ttk.Frame(main_frame, width=300)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)
        
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        header_frame = ttk.Frame(left_panel)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = ttk.Label(header_frame, text="Image to Painter", font=("Arial", 20, "bold"))
        title_label.pack()
        
        subtitle_label = ttk.Label(header_frame, text="Your Photo, Artist's Brush", font=("Arial", 10))
        subtitle_label.pack()
        
        upload_frame = ttk.LabelFrame(left_panel, text="Upload Image", padding=10)
        upload_frame.pack(fill=tk.X, pady=(0, 15))
        
        upload_btn = ttk.Button(upload_frame, text="Select Image", command=self.upload_image)
        upload_btn.pack(fill=tk.X, pady=(0, 5))
        
        drop_label = ttk.Label(upload_frame, text="Or drag and drop image here", foreground="gray")
        drop_label.pack()
        
        style_frame = ttk.LabelFrame(left_panel, text="Art Style", padding=10)
        style_frame.pack(fill=tk.X, pady=(0, 15))
        
        style_grid = ttk.Frame(style_frame)
        style_grid.pack(fill=tk.X)
        
        row, col = 0, 0
        for style_id, style_info in self.styles.items():
            btn = ttk.Button(style_grid, text=f"{style_info['icon']} {style_info['name']}",
                           command=lambda s=style_id: self.apply_style(s))
            btn.grid(row=row, column=col, padx=2, pady=2, sticky="ew")
            col += 1
            if col > 1:
                col = 0
                row += 1
        
        style_grid.columnconfigure(0, weight=1)
        style_grid.columnconfigure(1, weight=1)
        
        control_frame = ttk.LabelFrame(left_panel, text="Image Control", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(control_frame, text="Brightness:").pack(anchor=tk.W)
        self.brightness_var = tk.DoubleVar(value=1.0)
        brightness_scale = ttk.Scale(control_frame, from_=0.5, to=2.0, variable=self.brightness_var, command=self.adjust_brightness)
        brightness_scale.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(control_frame, text="Contrast:").pack(anchor=tk.W)
        self.contrast_var = tk.DoubleVar(value=1.0)
        contrast_scale = ttk.Scale(control_frame, from_=0.5, to=2.0, variable=self.contrast_var, command=self.adjust_contrast)
        contrast_scale.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(control_frame, text="Sharpness:").pack(anchor=tk.W)
        self.sharpness_var = tk.DoubleVar(value=0)
        sharpness_scale = ttk.Scale(control_frame, from_=0, to=5, variable=self.sharpness_var, command=self.adjust_sharpness)
        sharpness_scale.pack(fill=tk.X)
        
        action_frame = ttk.Frame(left_panel)
        action_frame.pack(fill=tk.X, pady=(0, 10))
        
        save_btn = ttk.Button(action_frame, text="Save Image", command=self.save_image, style="Accent.TButton")
        save_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        
        reset_btn = ttk.Button(action_frame, text="Reset", command=self.reset_image)
        reset_btn.pack(side=tk.RIGHT, expand=True, fill=tk.X)
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(left_panel, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))
        
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(left_panel, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_label.pack(fill=tk.X, pady=(10, 0))
        
        self.image_frame = ttk.Frame(right_panel, relief=tk.SUNKEN, borderwidth=2)
        self.image_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.image_frame, bg="#2b2b2b", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.create_text(400, 300, text="Upload an image", fill="gray", font=("Arial", 16))
        
        self.image_on_canvas = None
        
        self.canvas.bind("<Configure>", self.on_canvas_resize)
    
    def upload_image(self):
        file_path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp"),
                ("All files", "*.*")
            ]
        )
        
        if file_path:
            self.load_image(file_path)
    
    def load_image(self, file_path):
        try:
            file_size = os.path.getsize(file_path)
            if file_size > CONFIG["max_file_size"]:
                messagebox.showerror("Error", f"File size cannot exceed 10MB.\nCurrent size: {file_size/(1024*1024):.1f}MB")
                return
            
            self.image_path = file_path
            self.original_image = cv2.imread(file_path)
            
            if self.original_image is None:
                pil_image = Image.open(file_path)
                self.original_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            
            h, w = self.original_image.shape[:2]
            if w > 1200 or h > 800:
                scale = min(1200/w, 800/h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                self.original_image = cv2.resize(self.original_image, (new_w, new_h))
            
            self.current_image = self.original_image.copy()
            self.processed_image = None
            
            self.display_image(self.current_image)
            self.status_var.set(f"Loaded: {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image:\n{str(e)}")
    
    def display_image(self, image):
        if image is None:
            return
        
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width = 800
            canvas_height = 600
        
        h, w = image.shape[:2]
        scale = min(canvas_width/w, canvas_height/h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        resized = cv2.resize(image, (new_w, new_h))
        rgb_image = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_image)
        self.photo = ImageTk.PhotoImage(pil_image)
        
        self.canvas.delete("all")
        x = (canvas_width - new_w) // 2
        y = (canvas_height - new_h) // 2
        self.image_on_canvas = self.canvas.create_image(x, y, anchor=tk.NW, image=self.photo)
        self.displayed_image_size = (new_w, new_h)
    
    def on_canvas_resize(self, event):
        if hasattr(self, 'current_image') and self.current_image is not None:
            self.display_image(self.current_image)
    
    def apply_style(self, style_id):
        if self.current_image is None:
            messagebox.showwarning("Warning", "Please upload an image first")
            return
        
        if self.processing:
            return
        
        self.processing = True
        self.current_style.set(style_id)
        self.status_var.set(f"Applying {self.styles[style_id]['name']}...")
        
        thread = threading.Thread(target=self._process_style_thread, args=(style_id,))
        thread.daemon = True
        thread.start()
    
    def _process_style_thread(self, style_id):
        try:
            self.progress_queue.put(("progress", 30))
            style_func = self.styles[style_id]["func"]
            processed = style_func(self.original_image.copy())
            self.progress_queue.put(("progress", 80))
            self.processed_image = processed
            self.current_image = processed
            self.progress_queue.put(("progress", 100))
            self.progress_queue.put(("complete", style_id))
        except Exception as e:
            self.progress_queue.put(("error", str(e)))
    
    def check_progress_queue(self):
        try:
            while True:
                msg = self.progress_queue.get_nowait()
                
                if msg[0] == "progress":
                    self.progress_var.set(msg[1])
                elif msg[0] == "complete":
                    style_id = msg[1]
                    self.display_image(self.current_image)
                    self.status_var.set(f"{self.styles[style_id]['name']} applied successfully")
                    self.processing = False
                    self.root.after(1000, lambda: self.progress_var.set(0))
                elif msg[0] == "error":
                    messagebox.showerror("Error", f"Failed to apply style:\n{msg[1]}")
                    self.status_var.set("Error occurred")
                    self.processing = False
                    self.progress_var.set(0)
        except queue.Empty:
            pass
        
        self.root.after(100, self.check_progress_queue)
    
    def adjust_brightness(self, value):
        if self.original_image is None:
            return
        
        if self.processed_image is not None:
            base = self.processed_image
        else:
            base = self.original_image
        
        value = float(value)
        adjusted = cv2.convertScaleAbs(base, alpha=value, beta=0)
        self.current_image = adjusted
        self.display_image(adjusted)
    
    def adjust_contrast(self, value):
        if self.original_image is None:
            return
        
        if self.processed_image is not None:
            base = self.processed_image
        else:
            base = self.original_image
        
        value = float(value)
        adjusted = cv2.convertScaleAbs(base, alpha=1, beta=0)
        lab = cv2.cvtColor(adjusted, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=value, tileGridSize=(8,8))
        l = clahe.apply(l)
        lab = cv2.merge([l, a, b])
        adjusted = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        self.current_image = adjusted
        self.display_image(adjusted)
    
    def adjust_sharpness(self, value):
        if self.original_image is None:
            return
        
        if self.processed_image is not None:
            base = self.processed_image
        else:
            base = self.original_image
        
        value = float(value)
        if value > 0:
            kernel = np.array([[-1,-1,-1], [-1, 9+value,-1], [-1,-1,-1]]) / (1 + value)
            adjusted = cv2.filter2D(base, -1, kernel)
        else:
            adjusted = base
        
        self.current_image = adjusted
        self.display_image(adjusted)
    
    def save_image(self):
        if self.current_image is None:
            messagebox.showwarning("Warning", "No image to save")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        style_name = self.styles[self.current_style.get()]["name"].replace(" ", "_")
        default_name = f"portrait_{style_name}_{timestamp}.png"
        
        file_path = filedialog.asksaveasfilename(
            title="Save Image",
            defaultextension=".png",
            filetypes=[
                ("PNG Image", "*.png"),
                ("JPEG Image", "*.jpg"),
                ("All files", "*.*")
            ],
            initialfile=default_name
        )
        
        if file_path:
            try:
                rgb_image = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_image)
                pil_image.save(file_path)
                
                self.status_var.set(f"Saved: {os.path.basename(file_path)}")
                messagebox.showinfo("Success", "Image saved successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save image:\n{str(e)}")
    
    def reset_image(self):
        if self.original_image is not None:
            self.current_image = self.original_image.copy()
            self.processed_image = None
            self.display_image(self.current_image)
            self.status_var.set("Image reset")
            self.brightness_var.set(1.0)
            self.contrast_var.set(1.0)
            self.sharpness_var.set(0)
    
    def load_config(self):
        try:
            if os.path.exists(CONFIG["config_file"]):
                with open(CONFIG["config_file"], 'r', encoding='utf-8') as f:
                    config = json.load(f)
        except:
            pass
    
    def save_config(self):
        try:
            config = {"window_size": self.root.geometry()}
            with open(CONFIG["config_file"], 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except:
            pass

def main():
    root = tk.Tk()
    
    style = ttk.Style()
    style.theme_use('clam')
    style.configure("Accent.TButton", font=("Arial", 10, "bold"))
    
    app = PortraitAI(root)
    
    def on_closing():
        app.save_config()
        shutil.rmtree(CONFIG["temp_folder"], ignore_errors=True)
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()