import tkinter as tk
from PIL import ImageGrab


def save_widget_screenshot(app: tk.Tk, filename: str):
    """
    Save a screenshot of a tkinter widget to a PNG file.

    Example

        root = tk.Tk()
        widget = tk.Label(root, "Hello world")
        root.after(1000, lambda: save_widget_screenshot(root, 'hello_window.png'))
        root.after(2000, root.destroy)
        root.mainloop()

    :param app: tkinter app
    :param filename: filename of png file
    """

    # Get window coordinates
    app.update()
    x = app.winfo_rootx()
    y = app.winfo_rooty()
    width = app.winfo_width()
    height = app.winfo_height()
    print(f"widget location: ({x}, {y}), width={width}, height={height}")

    # grab image and save
    image = ImageGrab.grab(
        bbox=(x, y, x + width, y + height)
    )
    image.save(filename)