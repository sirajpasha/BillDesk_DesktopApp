"""Screenshots of the in-program Help screen (run after build_user_guide.py has made app/assets/help/guide.json)."""
import os
import sys

from qa_gui_common import *            # noqa: F401,F403
from PIL import ImageGrab

OUT = os.path.join(SCRATCH, "guide_img")
os.makedirs(OUT, exist_ok=True)

root, db, auth, billing, user, win = boot("admin", "admin123")
root.geometry("1380x880+10+10")
root.update()


def snap(name):
    shot(root, name)
    os.replace(os.path.join(SCRATCH, "shots", name + ".png"), os.path.join(OUT, name + ".png"))


win.show_page("New Bill")
pump(root, 8)
win._on_f9()                                    # F9 on New Bill: the help for that screen
pump(root, 12)
snap("120-help-this-screen")

hv = win.help_view
hv.query_var.set("how do I return goods")
hv.search()
pump(root, 12)
snap("121-help-search")
hv.query_var.set("")
hv.show_start()
pump(root, 8)
root.destroy()
print("images:", sorted(f for f in os.listdir(OUT) if f.startswith("12")))
