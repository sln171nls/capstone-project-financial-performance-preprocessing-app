from flask import Flask, request, render_template, send_file
import pandas as pd
import numpy as np
import os

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/', methods=['GET', 'POST'])
def upload_files():
    if request.method == 'POST':
        file1 = request.files['file1']
        file2 = request.files['file2']
        file3 = request.files['file3']

        path1 = os.path.join(UPLOAD_FOLDER, file1.filename)
        path2 = os.path.join(UPLOAD_FOLDER, file2.filename)
        path3 = os.path.join(UPLOAD_FOLDER, file3.filename)

        file1.save(path1)
        file2.save(path2)
        file3.save(path3)

        # Process files
        output_path = process_files(path1, path2, path3)

        return send_file(output_path, as_attachment=True)

    return render_template('upload.html')

def process_files(transactions_path, master_path, gic_path):
    transactions = pd.read_excel(transactions_path)
    master_sheet = pd.read_excel(master_path)
    gic_data = pd.read_excel(gic_path)

    transactions['Trade Date'] = pd.to_datetime(transactions['Trade Date'], errors='coerce')
    master_sheet['DATE'] = pd.to_datetime(master_sheet['DATE'], errors='coerce')
    transactions['Fund ID'] = transactions['Fund ID'].astype(str).str.zfill(3)
    transactions['Fund Code'] = transactions['Mgmt Code'] + transactions['Fund ID']
    transactions[['Gross Amount', 'Units/Shares']] = transactions[['Gross Amount', 'Units/Shares']].apply(pd.to_numeric, errors='coerce')

    output_data = []
    for fund_code in transactions['Fund Code'].unique():
        fund_transactions = transactions[transactions['Fund Code'] == fund_code].copy()
        fund_transactions.sort_values(by='Trade Date', inplace=True)
        units_held = 0
        Gross_amount = 0
        start_date = fund_transactions['Trade Date'].min()
        end_date = fund_transactions['Trade Date'].max()

        matched_fund_code = next((col for col in master_sheet.columns if fund_code.replace(' ', '') in col.replace(' ', '')), None)
        if matched_fund_code:
            fund_data = master_sheet[['DATE', matched_fund_code]].copy()
            fund_data = fund_data.rename(columns={matched_fund_code: 'Daily Rate'})
            fund_data['Daily Rate'] = pd.to_numeric(fund_data['Daily Rate'], errors='coerce')
            fund_data = fund_data[(fund_data['DATE'] >= start_date) & (fund_data['DATE'] <= end_date)]

            for _, entry in fund_data.iterrows():
                date = entry['DATE']
                daily_rate = entry['Daily Rate']
                trade_match = fund_transactions[fund_transactions['Trade Date'] == date]
                if not trade_match.empty:
                    units_held += trade_match['Units/Shares'].sum()
                    Gross_amount += trade_match['Gross Amount'].sum()
                portfolio_value = units_held * daily_rate
                output_data.append({'DATE': date, 'Client Name': fund_transactions.iloc[0]['Client Name'], 'Fund Code': fund_code, 'Gross Amount': Gross_amount, 'Portfolio Value': portfolio_value})

    final_data = pd.DataFrame(output_data)
    gic_data['Start date'] = pd.to_datetime(gic_data['Start date'], errors='coerce')
    gic_data['End date'] = pd.to_datetime(gic_data['End date'], errors='coerce')
    gic_data['Principal'] = pd.to_numeric(gic_data['Principal'].replace('[^\\d.]', '', regex=True), errors='coerce')
    gic_data['Rate %'] = pd.to_numeric(gic_data['Rate %'], errors='coerce') / 100

    gic_output = []
    for _, row in gic_data.iterrows():
        fund_code = row['Product'].strip()
        principal = row['Principal']
        start_date = row['Start date']
        end_date = row['End date']
        rate = row['Rate %']
        client_name = row.get('Client Name', 'Unknown')
        gic_fund_data = master_sheet[(master_sheet['DATE'] >= start_date) & (master_sheet['DATE'] <= end_date)][['DATE']].copy()
        if not gic_fund_data.empty:
            days_elapsed = (gic_fund_data['DATE'] - start_date).dt.days
            gic_fund_data['Daily Price'] = principal * ((1 + rate) ** (days_elapsed / 365))
            gic_fund_data['Gross Amount'] = principal
            gic_fund_data['Portfolio Value'] = gic_fund_data['Daily Price']
            gic_fund_data['Fund Code'] = fund_code
            gic_fund_data['Client Name'] = client_name
            gic_output.append(gic_fund_data)

    if gic_output:
        gic_final_data = pd.concat(gic_output, ignore_index=True)
    else:
        gic_final_data = pd.DataFrame(columns=['DATE', 'Client Name', 'Fund Code', 'Gross Amount', 'Portfolio Value'])

    combined_data = pd.concat([final_data, gic_final_data], ignore_index=True)
    output_file = os.path.join(UPLOAD_FOLDER, 'portfolio_performance_combined_gross.csv')
    combined_data.to_csv(output_file, index=False)

    return output_file

if __name__ == '__main__':
    app.run(debug=True)
