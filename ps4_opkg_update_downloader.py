import os
import re
import sys
import json
import traceback

import requests
from tqdm import tqdm
from bs4 import BeautifulSoup


def clean_up(path):
	if not path:
		path = "."
	for fname in os.listdir(path):
		if not fname.endswith('.incomplete_piece'):
			continue
		incom_path = os.path.join(path, fname)
		if os.path.isfile(incom_path):
			os.remove(incom_path)

def parse_cfg():
	with open('config.json') as f:
		return json.load(f)

def dir_setup(path):	
	if path and not os.path.isdir(path):
		os.makedirs(path)
		
def extract_cusa(path):
	sfo_path = os.path.join(path, 'app_param.sfo')
	with open(sfo_path, 'rb') as f:
		data = f.read()
		pos = data.find(b'\x43\x55\x53\x41')
		if pos == -1:
			raise Exception('Failed to find CUSA.')
		f.seek(pos)
		cusa = f.read(9).decode('ASCII')
	return cusa

def check_cusa(cusa):
	match = re.match('cusa-?\d{5}', cusa, re.IGNORECASE)
	if match:
		return True

def get_html(cusa):
	r = session.get("https://orbispatches.com/" + cusa)
	r.raise_for_status()
	return r.text

def parse_meta(html):
	parsed = {}
	soup = BeautifulSoup(html, 'html.parser')
	try:
		game_title = soup.find('h3', {'class': 'h3-title'}).text.strip()
	except AttributeError:
		raise Exception('Couldn\'t find any updates for specified CUSA.')
	containers = soup.find_all('div', {'class': 'patch-container'})
	for num, container in enumerate(containers, 1):
		rows = container.find_all('div', {'class': 'col-auto ml-auto py-2'})
		element = container.find('a', {'class': 'main'})
		parsed[num] = {'update_ver': element['data-version'], 'size': rows[0].text,
								'req_fware': rows[1].text.strip(), 'key': element['data-key']}
	print("--" + game_title + "--")
	return parsed

def print_meta(parsed_meta):
	print("ID\tUpdate version\tRequired firmware  Size")
	for k, v in parsed_meta.items():
		print("{}\t{update_ver}\t\t{req_fware}\t\t   {size}".format(k, **v))

def get_choice(parsed_meta):
	print_meta(parsed_meta)
	keys = parsed_meta.keys()
	while True:
		try:
			choice = int(input('Input ID: '))
		except ValueError:
			continue
		if choice in keys:
			print(parsed_meta[choice]['update_ver'], "chosen.")
			return parsed_meta[choice]['key']

def download_piece(url):	
	path = os.path.join(cfg['output_dir'], os.path.basename(url))
	if os.path.isfile(path):
		print("Piece already exists locally. Skipped.")
		return
	pre_path = path[0:-3] + "incomplete_piece"
	session.headers.update({'Range': 'bytes=0-'})
	r = session.get(url, stream=True)
	with open(pre_path, 'wb') as f:
		with tqdm(total=int(r.headers['Content-Length']), unit='B',
			unit_scale=True, unit_divisor=1024) as pb:
				for chunk in r.iter_content(2048 ** 2):
					if chunk:
						f.write(chunk)
						pb.update(len(chunk))
	os.rename(pre_path, path)

def get_urls(key):
	session.headers.update({'X-Requested-With': 'XMLHttpRequest'})
	r = session.post('https://orbispatches.com/api/patch.php', data={'key': key})
	del session.headers['X-Requested-With']
	r.raise_for_status()
	resp = r.json()
	if resp['success'] == False:
		raise Exception('Bad response.')
	return [url['pkg_url'] for url in resp['pieces']]
	
def merge_pieces(url, total):
	print("Merging pieces...")
	paths = []
	base_fname = os.path.basename(url)[0:-5]
	pb = tqdm(total=total,
			  bar_format='{l_bar}{bar}{n_fmt}/{total_fmt} [{elapsed}<{remaining}]')
	merged_path = os.path.join(cfg['output_dir'], base_fname + "merged.pkg")
	try:
		with open(merged_path, 'wb') as f1:
			# Force piece order just in case.
			for i in range(total):
				piece_path = os.path.join(cfg['output_dir'], "{}{}.pkg".format(base_fname, i))
				paths.append(piece_path)
				with open(piece_path, 'rb') as f2:
					while True:
						data = f2.read(2048 ** 2)
						if not data:
							pb.update(1)
							break
						f1.write(data)
	finally:
		pb.close()
	if cfg['delete_pieces'] == True:
		[os.remove(path) for path in paths]

def main(cusa):
	html = get_html(cusa)
	parsed_meta = parse_meta(html)
	key = get_choice(parsed_meta)
	urls = get_urls(key)
	total = len(urls)
	for num, url in enumerate(urls, 1):
		print("Downloading piece {} of {}:".format(num, total))
		download_piece(url)
	if cfg['merge'] == True:
		if total > 1:
			merge_pieces(urls[0], total)
		else:
			print("Merging skipped as there is only one piece.")

if __name__ == '__main__':
	session = requests.Session()
	session.headers.update({
		'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
					  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome'
					  '/75.0.3770.100 Safari/537.36'
	})
	try:
		if hasattr(sys, 'frozen'):
			os.chdir(os.path.dirname(sys.executable))
		else:
			os.chdir(os.path.dirname(__file__))
	except OSError:
		pass
	try:
		cfg = parse_cfg()
		clean_up(cfg['output_dir'])
		dir_setup(cfg['output_dir'])
		if len(sys.argv) > 1:
			cusa = extract_cusa(sys.argv[1])
		else:
			while True:
				cusa = input('Input CUSA: ')
				if not cusa.strip():
					continue
				elif check_cusa(cusa) == None:
					print("Invalid CUSA.")
					continue
				break
			cusa = cusa.replace('-', '').upper()
		main(cusa)
	except KeyboardInterrupt:
		pass
	except Exception:
		traceback.print_exc()
	finally:
		print("Press enter to exit.")
		input()
