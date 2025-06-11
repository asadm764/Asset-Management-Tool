import os
import subprocess
import shutil
import sys
import tempfile
import json
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QListWidget, QMessageBox, QInputDialog
)  
from PyQt6.QtGui import QPixmap

"""
IMPORTANT:
Do NOT run this script directly from your Perforce workspace.
Copy it to a local directory before executing.
"""

def is_running_in_perforce():
    # Update these paths to match your Perforce workspace roots
    perforce_roots = [
        r"C:\Perforce",  # Example Windows path
        "/Users/youruser/Perforce",  # Example macOS/Linux path
    ]
    script_path = os.path.abspath(__file__)
    for root in perforce_roots:
        if script_path.startswith(os.path.abspath(root)):
            return True
    return False

def is_in_perforce_workspace_by_marker():
    # Looks for a .p4config file in the script's directory or any parent directory
    path = os.path.abspath(__file__)
    while True:
        if os.path.exists(os.path.join(path, ".p4config")):
            return True
        new_path = os.path.dirname(path)
        if new_path == path:
            break
        path = new_path
    return False

def check_write_access():
    try:
        testfile = os.path.join(os.path.dirname(__file__), "p4_write_test.tmp")
        with open(testfile, "w") as f:
            f.write("test")
        os.remove(testfile)
        return True
    except Exception:
        return False

if is_running_in_perforce() or is_in_perforce_workspace_by_marker():
    print("ERROR: Please copy this script to a local directory before running. Do not run directly from Perforce workspace.")
    sys.exit(1)

if not check_write_access():
    print("ERROR: This directory is read-only. Please copy the script to a local, writable directory before running.")
    sys.exit(1)

# Introductory window shown at application startup
class IntroPage(QWidget):
    def __init__(self, on_proj_enter):
        super().__init__()
        self.setWindowTitle("VFX Machine Inc. PMT")
        self.setGeometry(800, 400, 200, 200)
        layout = QVBoxLayout()
        image = QLabel()
        pixmap = QPixmap("PMT_Company_Logo_White.png")
        image.setPixmap(pixmap)
        layout.addWidget(image)
        projects_btn = QPushButton("Enter Asset Manager")
        projects_btn.clicked.connect(on_proj_enter)
        layout.addWidget(projects_btn)
        self.setLayout(layout)

        self.company_assets_window = None  # Keep a reference

    def show_company_assets(self):
        # Show the company assets window if it exists, otherwise bring it to the front
        if self.company_assets_window is None or not self.company_assets_window.isVisible():
            self.company_assets_window.show()
        else:
            self.company_assets_window.raise_()
            self.company_assets_window.activateWindow()

# Window for displaying project/category/asset hierarchies
class HierarchyWindow(QWidget):
    def __init__(
        self, title, items, slot, asset_actions=False, edit_slot=None,
        delete_slot=None, create_slot=None, info_slot=None, back_slot=None
    ):
        super().__init__()
        self.setWindowTitle(title)
        self.setGeometry(800, 400, 400, 300)
        self.layout = QVBoxLayout()
        label = QLabel(title)
        self.layout.addWidget(label)

        # Add create asset button if applicable
        if create_slot:
            create_btn = QPushButton("Create Asset")
            create_btn.clicked.connect(create_slot)
            self.layout.addWidget(create_btn)

        # Add items as buttons or asset rows
        for item in items:
            if asset_actions:
                self.add_asset_row(item, info_slot, edit_slot, delete_slot)
            else:
                btn = QPushButton(item)
                btn.clicked.connect(slot)
                self.layout.addWidget(btn)

        # Add back and exit buttons if applicable
        if back_slot:
            bottom_row = QHBoxLayout()
            back_btn = QPushButton("Back")
            back_btn.clicked.connect(back_slot)
            bottom_row.addWidget(back_btn)

            exit_btn = QPushButton("Exit")
            exit_btn.clicked.connect(self.confirm_exit)
            bottom_row.addWidget(exit_btn)

            bottom_container = QWidget()
            bottom_container.setLayout(bottom_row)
            self.layout.addWidget(bottom_container)

        self.setLayout(self.layout)

    def add_asset_row(self, item, info_slot, edit_slot, delete_slot):
        # Add a row for an asset with Open, Rename, and Delete buttons
        row = QHBoxLayout()
        asset_label = QLabel(item)
        row.addWidget(asset_label)
        for label, slot in [("Open", info_slot), ("Rename", edit_slot), ("Delete", delete_slot)]:
            btn = QPushButton(label)
            btn.setProperty("asset_name", item)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        container = QWidget()
        container.setLayout(row)
        self.layout.addWidget(container)

    def confirm_exit(self):
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Are you sure you want to exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            QApplication.instance().quit()

# Main UI for managing projects and assets
class ProjectManagerUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Project Management Tool")
        self.setGeometry(800, 400, 500, 300)

        self.HC = HoudiniConnection()

        layout = QVBoxLayout()

        self.label = QLabel("Company Assets")
        layout.addWidget(self.label)

        self.project_name_input = QLineEdit()
        self.project_name_input.setPlaceholderText("Enter Project Name")
        layout.addWidget(self.project_name_input)

        # Create Project button
        create_btn = QPushButton("Create Project")
        create_btn.clicked.connect(self.add_project)
        layout.addWidget(create_btn)

        self.projects_list = QListWidget()
        layout.addWidget(self.projects_list)

        # Project management buttons
        buttons = [
            ("Enter Project", self.enter_selected_project),
            ("Rename Project", self.rename_project),
            ("Delete Project", self.delete_project),
            ("Exit", QApplication.instance().quit)
        ]
        for label, slot in buttons:
            button = QPushButton(label)
            button.clicked.connect(slot)
            layout.addWidget(button)

        self.setLayout(layout)
        self.projects = []

        # Ensure config folder exists or copy PMT.json 
        self.config_folder = os.path.join(tempfile.gettempdir(), "PMT_Projects")
        os.makedirs(self.config_folder, exist_ok=True)
        self.config_json_path = os.path.join(self.config_folder, "PMT.json")

        # Copy PMT.json from solution directory if not present in config folder
        solution_json_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "PMT.json")
        if not os.path.exists(self.config_json_path):
            if os.path.exists(solution_json_path):
                shutil.copy2(solution_json_path, self.config_json_path)
            else:
                # If not found, create an empty JSON structure
                with open(self.config_json_path, "w") as f:
                    json.dump({}, f, indent=4)

        # Load asset hierarchy from JSON file
        self.assets_hierarchy = self.load_assets_from_json()
        self.naming_conventions = self.assets_hierarchy.pop("naming_conventions", {})

        # Ensure Company Assets always exists
        if "Master Assets" not in self.assets_hierarchy:
            self.assets_hierarchy["Master Assets"] = {
                "Company Logo": [],
                "Marketing Materials": [],
                "Master Materials": [],
                "Master Textures": [],
                "Master Assets": []
            }

        self.selected_project = None
        self.selected_category = None

        # Ensure Company Assets is always first in the list
        self.projects = list(self.assets_hierarchy.keys())
        if "Master Assets" in self.projects:
            self.projects.remove("Master Assets")
            self.projects.insert(0, "Master Assets")
        self.projects_list.clear()
        for project in self.projects:
            self.projects_list.addItem(project)

    def view_comp_assets(self):
        # Set the selected project to 'Master Assets' and show its categories
        self.selected_project = "Master Assets"
        self.back_to_categories()

    def get_assets(self, project, category):
        # Return the list of assets for a given project and category
        cat_val = self.assets_hierarchy[project][category]
        if isinstance(cat_val, dict) and "assets" in cat_val:
            return cat_val["assets"]
        return cat_val

    def get_display_names(self, assets):
        # Return a list of display names for a list of asset dictionaries
        return [a["display_name"] for a in assets]

    def find_asset_by_display_name(self, assets, display_name):
        # Find and return an asset dictionary by its display name
        for a in assets:
            if a["display_name"] == display_name:
                return a
        return None

    def add_project(self):
        # Add a new project to the hierarchy and update the UI
        project_name = self.project_name_input.text().strip()
        if project_name:
            if project_name == "Master Assets":
                QMessageBox.warning(self, "Warning", "Cannot use reserved name 'Company Assets'.")
                return
            if project_name not in self.projects:
                self.projects.append(project_name)
                self.projects_list.addItem(project_name)
                self.project_name_input.clear()
                if project_name not in self.assets_hierarchy:
                    self.assets_hierarchy[project_name] = {
                        "Static Meshes": [],
                        "Textures": [],
                        "Simulations": [],
                        "Flipbooks": []
                    }
                    self.save_assets_to_json()
            else:
                QMessageBox.warning(self, "Warning", "Project already exists.")
        else:
            QMessageBox.warning(self, "Warning", "Please enter a project name.")

    def rename_project(self):
        # Rename the selected project in the hierarchy and update the UI and filesystem
        selected_items = self.projects_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a project to rename.")
            return

        old_name = selected_items[0].text()
        if old_name == "Master Assets":
            QMessageBox.warning(self, "Warning", "Cannot rename Company Assets.")
            return

        new_name, ok = QInputDialog.getText(
            self, "Rename Project", f"Rename project '{old_name}' to:"
        )

        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, "Warning", "Project name cannot be empty.")
                return

            if new_name in self.projects or new_name == "Master Assets":
                QMessageBox.warning(self, "Warning", "Project name already exists or is reserved.")
                return

            idx = self.projects.index(old_name)
            self.projects[idx] = new_name
            self.projects_list.item(idx).setText(new_name)
            self.assets_hierarchy[new_name] = self.assets_hierarchy.pop(old_name)

            # Rename the project folder
            root_dir = os.path.join(tempfile.gettempdir(), "PMT_Projects")
            old_project_path = os.path.join(root_dir, old_name)
            new_project_path = os.path.join(root_dir, new_name)
            if os.path.exists(old_project_path):
                try:
                    os.rename(old_project_path, new_project_path)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to rename project folder: {e}")

            self.save_assets_to_json()
            QMessageBox.information(
                self, "Project Renamed", f"Project renamed to '{new_name}'."
            )

    def load_assets_from_json(self):
        # Load the asset hierarchy from the JSON file in the config folder
        try:
            with open(self.config_json_path, "r") as f:
                data = json.load(f)
            # Migrate all assets to dict format and rename 'Meshes' to 'Static Meshes'
            for project, categories in data.items():
                if project == "naming_conventions":
                    continue
                if "Meshes" in categories:
                    categories["Static Meshes"] = categories.pop("Meshes")
                for cat, assets in categories.items():
                    if isinstance(assets, dict) and "assets" in assets:
                        asset_list = assets["assets"]
                    else:
                        asset_list = assets
                    for i, a in enumerate(asset_list):
                        if isinstance(a, str):
                            asset_list[i] = {"display_name": a, "db_name": a.replace(" ", "")}
            # Also migrate naming_conventions key if needed
            if "naming_conventions" in data and "Meshes" in data["naming_conventions"]:
                data["naming_conventions"]["Static Meshes"] = data["naming_conventions"].pop("Meshes")
            return data
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load hierarchy: {e}")
            return {}

    def save_assets_to_json(self):
        # Save the asset hierarchy to the JSON file in the config folder and sync the filesystem
        try:
            data = dict(self.assets_hierarchy)
            data["naming_conventions"] = self.naming_conventions
            with open(self.config_json_path, "w") as f:
                json.dump(data, f, indent=4)
            self.sync_filesystem_with_json()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save hierarchy: {e}")

    def enter_selected_project(self):
        # Enter the selected project and show its categories
        selected_items = self.projects_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a project to enter.")
            return

        self.selected_project = selected_items[0].text()
        self.back_to_categories()

    def delete_project(self):
        # Delete the selected project from the hierarchy and update the UI
        selected_items = self.projects_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a project to delete.")
            return
        project_name = selected_items[0].text()
        if project_name == "Master Assets":
            QMessageBox.warning(self, "Warning", "Cannot delete Company Assets.")
            return
        if QMessageBox.question(
            self, "Confirm Delete", f"Are you sure you want to delete project '{project_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            idx = self.projects.index(project_name)
            self.projects_list.takeItem(idx)
            del self.assets_hierarchy[project_name]
            self.projects.remove(project_name)
            self.save_assets_to_json()
            QMessageBox.information(self, "Project Deleted", f"Project '{project_name}' deleted.")

    def back_to_projects(self):
        # Close the category window and return to the project selection screen
        if hasattr(self, 'category_window_hierarchy'):
            self.category_window_hierarchy.close()

    def back_to_categories(self):
        # Close the asset window and show the category selection window for the selected project
        if hasattr(self, 'asset_window_hierarchy'):
            self.asset_window_hierarchy.close()

        categories = list(self.assets_hierarchy[self.selected_project].keys())
        self.category_window_hierarchy = HierarchyWindow(
            f"Project: {self.selected_project} - Select Category",
            categories,
            self.category_button_clicked,
            back_slot=self.back_to_projects
        )
        self.category_window_hierarchy.show()

    def category_button_clicked(self):
        # Handle category button click and show the assets in the selected category
        button = self.sender()
        self.selected_category = button.text()
        self.show_asset_buttons(self.selected_category)

    def show_asset_buttons(self, category):
        # Show the asset management window for the selected category
        self.selected_category = category
        assets = self.get_assets(self.selected_project, self.selected_category)
        display_names = self.get_display_names(assets)
        self.asset_window_hierarchy = HierarchyWindow(
            f"{self.selected_project} / {self.selected_category} - Assets",
            display_names,
            self.asset_button_clicked,
            asset_actions=True,
            edit_slot=self.edit_asset_clicked,
            delete_slot=self.delete_asset_clicked,
            create_slot=self.create_asset_clicked,
            info_slot=self.asset_button_clicked,
            back_slot=self.back_to_categories
        )
        self.asset_window_hierarchy.show()

    def asset_button_clicked(self):
        # Handle asset button click to open the asset in Houdini
        button = self.sender()
        display_name = button.property("asset_name")
        assets = self.get_assets(self.selected_project, self.selected_category)
        asset = self.find_asset_by_display_name(assets, display_name)
        db_name = asset["db_name"]

        # Set HoudiniConnection properties
        self.HC.project_name = self.selected_project
        self.HC.project_category = self.selected_category
        self.HC.asset_name = db_name

        # Open the Houdini file
        QMessageBox.information(self, "Reminder", "Please keep PMT open while working in Houdini")
        self.HC.open_houdini_with_file()

    def create_asset_clicked(self):
        # Create a new asset in the selected category
        display_name, ok = QInputDialog.getText(self, "Create Asset", f"{self.selected_category}: Enter Name:")
        print(f"Please wait a moment for asset to be created...")
        if not (ok and display_name):
            return

        convention = self.naming_conventions.get(self.selected_category, {})
        prefix = convention.get("prefix", "")
        suffix = convention.get("suffix", "")

        if self.selected_category == "Textures" and "suffixes" in convention:
            suffix_keys = list(convention["suffixes"].keys())
            suffix_type, ok = QInputDialog.getItem(
                self, "Texture Type", "Select texture type:", suffix_keys, 0, False
            )
            if not ok:
                return
            suffix = convention["suffixes"][suffix_type]

        db_name = f"{prefix}{display_name.replace(' ', '')}{suffix}"
        assets = self.get_assets(self.selected_project, self.selected_category)
        if any(a["db_name"] == db_name for a in assets):
            QMessageBox.warning(self, "Duplicate", "Asset name already exists.")
            return

        assets.append({"display_name": display_name, "db_name": db_name})
        self.save_assets_to_json()

        self.HC.project_name = self.selected_project
        self.HC.project_category = self.selected_category
        self.HC.asset_name = db_name
        if self.HC.check_houdini_version():
            self.HC.create_new_file()

        QMessageBox.information(self, "Asset Created", f"Asset '{display_name}' created.")
        self.show_asset_buttons(self.selected_category)

    def edit_asset_clicked(self):
        # Edit (rename) the selected asset in the current category
        button = self.sender()
        display_name = button.property("asset_name")
        assets = self.get_assets(self.selected_project, self.selected_category)
        asset = self.find_asset_by_display_name(assets, display_name)
        if not asset:
            QMessageBox.warning(self, "Error", f"Asset '{display_name}' not found.")
            return

        new_display_name, ok = QInputDialog.getText(
            self, f"{self.selected_category}: Edit Asset", f"Rename '{display_name}' to:"
        )
        if not (ok and new_display_name):
            return

        convention = self.naming_conventions.get(self.selected_category, {})
        prefix = convention.get("prefix", "")
        suffix = convention.get("suffix", "")

        if self.selected_category == "Textures" and "suffixes" in convention:
            suffix_keys = list(convention["suffixes"].keys())
            suffix_type, ok = QInputDialog.getItem(
                self, "Texture Type", "Select texture type:", suffix_keys, 0, False
            )
            if not ok:
                return
            suffix = convention["suffixes"][suffix_type]

        new_db_name = f"{prefix}{new_display_name.replace(' ', '')}{suffix}"
        if any(a["db_name"] == new_db_name for a in assets if a != asset):
            QMessageBox.warning(self, "Duplicate", "Asset name already exists.")
            return

        # Rename the asset in the hierarchy and on disk
        old_db_name = asset["db_name"]
        old_file_path = os.path.join(
            self.HC.project_path,
            self.selected_project,
            self.selected_category,
            old_db_name,
            f"{old_db_name}.hipnc"
        )
        new_file_path = os.path.join(
            self.HC.project_path,
            self.selected_project,
            self.selected_category,
            old_db_name,  # Folder is still old_db_name for now
            f"{new_db_name}.hipnc"
        )

        # If the file exists, rename it
        if os.path.exists(old_file_path):
            try:
                os.rename(old_file_path, new_file_path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to rename Houdini file: {e}")

        # Rename the asset folder
        old_asset_folder = os.path.join(
            self.HC.project_path,
            self.selected_project,
            self.selected_category,
            old_db_name
        )
        new_asset_folder = os.path.join(
            self.HC.project_path,
            self.selected_project,
            self.selected_category,
            new_db_name
        )
        if os.path.exists(old_asset_folder):
            try:
                os.rename(old_asset_folder, new_asset_folder)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to rename asset folder: {e}")

        # Update asset info in memory
        asset["display_name"] = new_display_name
        asset["db_name"] = new_db_name

        self.save_assets_to_json()
        QMessageBox.information(self, "Asset Renamed", f"Asset renamed to '{new_display_name}'.")
        self.show_asset_buttons(self.selected_category)

    def delete_asset_clicked(self):
        # Delete the selected asset from the current category after confirmation
        button = self.sender()
        display_name = button.property("asset_name")
        assets = self.get_assets(self.selected_project, self.selected_category)
        asset = self.find_asset_by_display_name(assets, display_name)
        if asset:
            confirm = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete asset '{display_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                assets.remove(asset)
                self.save_assets_to_json()
                QMessageBox.information(self, "Asset Deleted", f"Asset '{display_name}' deleted.")
                self.show_asset_buttons(self.selected_category)
        else:
            QMessageBox.warning(self, "Error", f"Asset '{display_name}' not found in list.")

    def sync_filesystem_with_json(self, root_dir=None):
        # Synchronize the filesystem structure with the asset hierarchy in JSON
        if root_dir is None:
            root_dir = os.path.join(tempfile.gettempdir(), "PMT_Projects")

        os.makedirs(root_dir, exist_ok=True)

        for project, categories in self.assets_hierarchy.items():
            project_path = os.path.join(root_dir, project)
            os.makedirs(project_path, exist_ok=True)

            for category, assets in categories.items():
                category_path = os.path.join(project_path, category)
                os.makedirs(category_path, exist_ok=True)

                if isinstance(assets, dict) and "assets" in assets:
                    asset_list = assets["assets"]
                else:
                    asset_list = assets

        self.cleanup_filesystem(root_dir)
        self.create_hidden_folders(root_dir)

    def cleanup_filesystem(self, root_dir):
        # Remove any folders or files from the filesystem that are not present in the asset hierarchy
        for project_folder in os.listdir(root_dir):
            project_path = os.path.join(root_dir, project_folder)
            if not os.path.isdir(project_path):
                continue

            if project_folder not in self.assets_hierarchy:
                shutil.rmtree(project_path)
                continue

            for category_folder in os.listdir(project_path):
                category_path = os.path.join(project_path, category_folder)
                if not os.path.isdir(category_path):
                    continue

                if category_folder not in self.assets_hierarchy[project_folder]:
                    shutil.rmtree(category_path)
                    continue

                cat_val = self.assets_hierarchy[project_folder][category_folder]
                if isinstance(cat_val, dict) and "assets" in cat_val:
                    asset_list = cat_val["assets"]
                else:
                    asset_list = cat_val

                db_names = set(a["db_name"] for a in asset_list)
                for asset_file in os.listdir(category_path):
                    asset_name, ext = os.path.splitext(asset_file)
                    if ext == ".txt" and asset_name not in db_names:
                        os.remove(os.path.join(category_path, asset_file))

    def create_hidden_folders(self, root_dir):
        # Create hidden folders (__temp, __tools, __config) at project, category, and asset levels
        hidden_folders = ["__temp", "__tools", "__config"]

        for project in self.assets_hierarchy:
            project_path = os.path.join(root_dir, project)
            # Project-level hidden folders
            for folder in hidden_folders:
                os.makedirs(os.path.join(project_path, folder), exist_ok=True)

            for category in self.assets_hierarchy[project]:
                category_path = os.path.join(project_path, category)
                # Category-level hidden folders
                for folder in hidden_folders:
                    os.makedirs(os.path.join(category_path, folder), exist_ok=True)

                assets = self.get_assets(project, category)
                for asset in assets:
                    db_name = asset["db_name"]
                    asset_folder = os.path.join(category_path, db_name)
                    os.makedirs(asset_folder, exist_ok=True)
                    # Asset-level hidden folders
                    for folder in hidden_folders:
                        os.makedirs(os.path.join(asset_folder, folder), exist_ok=True)


# Handles Houdini file operations and launching Houdini
class HoudiniConnection():  
    def __init__(self):  
        # Initialize Houdini connection and set up project path
        self.local_appdata = os.getenv('LOCALAPPDATA')
        self.project_path = os.path.join(self.local_appdata, "Temp", "PMT_Projects")
        self.hou_version = None  
        self.hou_file_path = None  
        self.project_name = None
        self.project_category = None
        self.asset_name = None 

    def check_houdini_version(self):  
        # Check for supported Houdini versions installed on the system
        hou_version_list = ["Houdini 20.5.550", "Houdini 20.5.445", "Houdini 20.5.332"]  
        #hou_version_list = ["Houdini 18.5.550"] testing with older version
        for version in hou_version_list:  
            houdini_exe = fr"C:\Program Files\Side Effects Software\{version}\bin\houdini.exe"  
            if os.path.exists(houdini_exe):  
                print(f"Using {version}.")  
                self.hou_version = version  
                return True  
        if self.hou_version is None:
            QMessageBox.warning(None, "Error", "No supported Houdini Version found.\nInstall latest version 20.5.550 to continue.")  
        return False  

    def write_hython_script(self, hip_path, script_dir=None):  
        # Write a hython script to save a Houdini file at the specified path
        if script_dir is None:
            if self.project_name is None or self.project_category is None or self.asset_name is None:
                script_dir = os.path.join(self.project_path, "__config")
            else:
                script_dir = os.path.join(
                    self.project_path,
                    self.project_name,
                    self.project_category,
                    self.asset_name,
                    "__config"
                )
        if not os.path.exists(script_dir):  
            os.makedirs(script_dir)  
        script_content = f"""import hou  
hou.hipFile.save(r"{hip_path}")"""  
        script_path = os.path.join(script_dir, f"{self.asset_name}_Config.py")  
        with open(script_path, "w") as f:  
            f.write(script_content)  
        return script_path  

    def create_new_file(self):  
        # Create a new Houdini file for the current asset
        if self.project_name and self.project_category and self.asset_name:
            new_file_path = os.path.join(
                self.project_path,
                self.project_name,
                self.project_category,
                self.asset_name,
                self.asset_name + ".hipnc"
            )
        else:
            #new_file_path = os.path.join(self.project_path, "TestFile.hipnc")     Create File Test
            return
        hython_path = fr"C:\Program Files\Side Effects Software\{self.hou_version}\bin\hython.exe"  
        script_path = self.write_hython_script(new_file_path)  
        subprocess.run([hython_path, script_path])  
        #print(f"New Houdini file created at: {new_file_path}") debugging file path

    def get_file_path(self):  
        # Get the file path for the current Houdini asset
        if self.project_name and self.project_category and self.asset_name:  
            self.hou_file_path = os.path.join(
                self.project_path,
                self.project_name,
                self.project_category,
                self.asset_name,
                f"{self.asset_name}.hipnc"
            )
        else:  
            self.hou_file_path = os.path.join(
                self.project_path,
                "DefaultProject",
                "DefaultCategory",
                "DefaultAsset",
                "DefaultAsset.hipnc"
            )
        return self.hou_file_path  

    def open_houdini_with_file(self):  
        # Open Houdini with the current asset file, if available
        if not self.check_houdini_version():  
            print("No Houdini version is set. Please check the Houdini version first.")  
            return  

        self.get_file_path()  

        if self.hou_version:  
            houdini_exe = fr"C:\Program Files\Side Effects Software\{self.hou_version}\bin\houdini.exe"  
            if os.path.exists(houdini_exe):  
                if os.path.exists(self.hou_file_path):  
                    subprocess.run([houdini_exe, self.hou_file_path])  
                else:  
                    print("Houdini file not found at the specified path:", self.hou_file_path)  
            else:  
                print("Houdini executable not found at the specified path:", houdini_exe)

if __name__ == "__main__":
    # Ensure PMT_Projects folder exists at startup
    import tempfile
    import os

    pmt_folder = os.path.join(tempfile.gettempdir(), "PMT_Projects")
    os.makedirs(pmt_folder, exist_ok=True)

    # Ensure Master Assets folder and its subfolders exist
    master_assets_folder = os.path.join(pmt_folder, "Master Assets")
    os.makedirs(master_assets_folder, exist_ok=True)
    master_subfolders = [
        "Company Logo",
        "Marketing Materials",
        "Master Materials",
        "Master Textures",
        "Master Assets"
    ]
    for subfolder in master_subfolders:
        os.makedirs(os.path.join(master_assets_folder, subfolder), exist_ok=True)

    app = QApplication(sys.argv)

    # Master stylesheet for all windows
    master_stylesheet = """
        QWidget {
            background-color: #23272e;
            color: #e0e0e0;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
        }
        QLabel {
            font-size: 16px;
            color: #f0f0f0;
        }
        QPushButton {
            background-color: #3a3f4b;
            color: #e0e0e0;
            border: 1px solid #444;
            border-radius: 4px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #50576a;
        }
        QLineEdit, QListWidget {
            background-color: #2c313c;
            color: #e0e0e0;
            border: 1px solid #444;
            border-radius: 4px;
        }
        QInputDialog {
            background-color: #23272e;
        }
        QMessageBox {
            background-color: #23272e;
        }
    """
    app.setStyleSheet(master_stylesheet)

    def show_main():
        # Show the main project manager UI after closing the intro page
        intro.close()
        window = ProjectManagerUI()
        window.show()
        app.main_window = window

    intro = IntroPage(show_main)
    intro.show()
    sys.exit(app.exec())
