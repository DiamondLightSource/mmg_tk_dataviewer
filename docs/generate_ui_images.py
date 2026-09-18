"""
Generate tk widget images
"""


from mmg_tk_dataviewer.misc.screenshot import save_widget_screenshot
from mmg_tk_dataviewer.misc.styles import create_root
from mmg_tk_dataviewer.misc.config import default_config, C


FOLDER = '/dls/science/groups/das/ExampleData/i16/azimuths'
FILE = '/dls/science/groups/das/ExampleData/i16/azimuths/1108607.nxs'


# config file
config = default_config()


# 1. TitleWindow
from mmg_tk_dataviewer.widgets.title_window import TitleWindow

root = create_root('test')
widget = TitleWindow(root, config)
root.after(1000, lambda: save_widget_screenshot(root, 'images/title_window.png'))
root.after(2000, root.destroy)
root.mainloop()

# 2. NeXus file viewer
from mmg_tk_dataviewer.widgets.hdf_viewer import HDFViewer

root = create_root('test')
widget = HDFViewer(root, FILE, config)
widget.expandall.set(True)
widget.check_expand()
root.after(1000, lambda: save_widget_screenshot(root, 'images/hdf_viewer.png'))
root.after(2000, root.destroy)
root.mainloop()


# 3. Folder Viewer
from mmg_tk_dataviewer.widgets.nexus_data_viewer import NexusDataViewer

root = create_root('test')
widget = NexusDataViewer(root, FOLDER, config)
root.after(1000, lambda: save_widget_screenshot(root, 'images/data_viewer.png'))
root.after(2000, root.destroy)
root.mainloop()