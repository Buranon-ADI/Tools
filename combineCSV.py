import os
import csv
import tkinter as tk
from tkinter import filedialog, messagebox
from openpyxl import Workbook

class CSVCombinerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CSV to Excel Combiner (With Summary)")
        self.root.geometry("500x240")

        self.folder_path = tk.StringVar()

        tk.Label(root, text="Selected Folder:").pack(pady=5)
        tk.Label(root, textvariable=self.folder_path, wraplength=460).pack()

        tk.Button(root, text="Select Folder", command=self.select_folder).pack(pady=10)
        tk.Button(root, text="Combine CSVs", command=self.combine_csvs).pack(pady=10)

    def select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing CSV Files")
        if folder:
            self.folder_path.set(folder)

    def combine_csvs(self):
        folder = self.folder_path.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder first.")
            return

        csv_files = [f for f in os.listdir(folder) if f.lower().endswith(".csv")]
        if not csv_files:
            messagebox.showerror("Error", "No CSV files found.")
            return

        wb = Workbook()
        combined_ws = wb.active
        combined_ws.title = "Combined"
        summary_ws = wb.create_sheet("Summary")

        header_written = False
        summary_results = {}  # source_file -> Pass/Fail

        try:
            for file in csv_files:
                file_path = os.path.join(folder, file)
                summary_results[file] = "Pass"  # default

                with open(file_path, newline="", encoding="utf-8") as csvfile:
                    reader = csv.reader(csvfile)

                    for row_index, row in enumerate(reader):
                        if row_index == 0:
                            if not header_written:
                                combined_ws.append(row + ["source_file"])
                                header_written = True
                        else:
                            combined_ws.append(row + [file])

                            # Column C = index 2 → Result
                            if len(row) > 2 and row[2].strip().lower() == "fail":
                                summary_results[file] = "Fail"

            # Write Summary Sheet
            summary_ws.append(["source_file", "Final Result"])
            for source_file, result in summary_results.items():
                summary_ws.append([source_file, result])

            output_path = os.path.join(folder, "combined_output.xlsx")
            wb.save(output_path)

            messagebox.showinfo(
                "Success",
                f"Excel file created successfully:\n{output_path}"
            )

        except Exception as e:
            messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = CSVCombinerApp(root)
    root.mainloop()
