# -*- coding: utf-8 -*-
"""experiment_baseline_duplicate_tonyX.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1rDPxopw_ZkcZprXp2Iu9JPHBbTCRuYD1
"""

# clone repo for dataset
# !git clone https://github.com/naufalizza/tugas-akhir-multilingual-document-similarity

# !pip install sentencepiece

# !pip install transformers torch tqdm numpy pandas

# from google.colab import drive
# drive.mount('/content/drive')

# !pwd

# import shutil

# Path to the model file in your Colab directory
MODEL_PATH = "./baseline_model"

# Destination path in your Google Drive
# DRIVE_MODEL_PATH = f'/content/drive/MyDrive/TA/{MODEL_PATH.split("/")[-1]}'

# load dataset
import pickle, os

DATA_PATH = "./compiled_data"

train_data_path = os.path.join(DATA_PATH, "train_data_with_augment.pickle")
eval_data_path = os.path.join(DATA_PATH, "eval_data.pickle")

with open(train_data_path, "rb") as f:
  train_data = pickle.load(f)
with open(eval_data_path, "rb") as f:
  eval_data = pickle.load(f)

import torch
from transformers import XLMRobertaConfig, XLMRobertaModel, XLMRobertaTokenizer, AdamW, get_cosine_schedule_with_warmup

# MODEL_NAME = "FacebookAI/xlm-roberta-base"
MODEL_NAME = "FacebookAI/xlm-roberta-large"
COMBINED_TOKENS_SIZE = 512
# COMBINED_TOKENS_SIZE = 768

model_config = XLMRobertaConfig.from_pretrained(MODEL_NAME)
tokenizer = XLMRobertaTokenizer.from_pretrained(MODEL_NAME)
backbone = XLMRobertaModel.from_pretrained(MODEL_NAME)

backbone

"""## PREPARE DATASET"""

# PREPARE DATASET
# helper function
import re

HEAD_TOKEN_RATIO = 100/128
HEAD_TOKEN_LENGTH = int((COMBINED_TOKENS_SIZE/2)*(HEAD_TOKEN_RATIO))
TAIL_TOKEN_LENGTH = int((COMBINED_TOKENS_SIZE/2)*(1-HEAD_TOKEN_RATIO))

print(f'{COMBINED_TOKENS_SIZE=}, {HEAD_TOKEN_LENGTH=}, {TAIL_TOKEN_LENGTH=}')


def mask_urls(text, placeholder="[URL]"):
    # Define a regular expression pattern to match URLs
    url_pattern = re.compile(r'https?://\S+|www\.\S+')

    # Find all matches of the URL pattern in the text
    matches = re.finditer(url_pattern, text)

    # Replace each URL with the placeholder text
    masked_text = url_pattern.sub(placeholder, text)

    return masked_text

def trunc_text(text, tokenizer, head_token_length=HEAD_TOKEN_LENGTH, tail_token_length=TAIL_TOKEN_LENGTH):
    # Tokenize the text
    tokens = tokenizer(
        text,
        truncation=True,
        return_tensors="pt"
    )

    # Get the input_ids tensor
    input_ids = tokens["input_ids"]

    end_idx = input_ids.shape[1]-1 # assume </s> token is last, exclude this token
    head_tokens = input_ids[:, 1:head_token_length+1]
    tail_tokens = input_ids[:, -tail_token_length+end_idx-1:end_idx-1]

    combined_fixed_length_tokens = torch.cat((head_tokens, tail_tokens), dim=1)

    truncated_text = tokenizer.decode(combined_fixed_length_tokens[0], skip_special_tokens = True)
    return truncated_text

# buat torch dataset
from torch.utils.data import Dataset, DataLoader

class DS(Dataset):
  global tokenizer
  def __init__(self, data):
    self.data = data

  def __len__(self):
    return len(self.data)

  def __getitem__(self, i):
    return ("\n----\n".join((mask_urls(trunc_text("\n".join(self.data[i][1]), tokenizer)),
                             mask_urls(trunc_text("\n".join(self.data[i][2]), tokenizer)))),
            torch.tensor([float(label) for label in self.data[i][3]])) # ini karena panjang bgt dokumennya, dikonkatenasi title dokumen 1 dan title dokumen 2

train_ds = DS(train_data)
eval_ds = DS(eval_data)

sample_train_ds = DS(train_data[:50])
sample_eval_ds = DS(eval_data[:100])

# for idx, data in enumerate(train_ds):
#     print(idx)
#     assert(len(data[0]) > 0)
#     assert(len(data[1]) == 7)

# for idx, data in enumerate(eval_ds):
#     print(idx)
#     assert(len(data[0]) > 0)
#     assert(len(data[1]) == 7)

# train_ds = sample_train_ds
# eval_ds = sample_eval_ds

"""## Model Class"""

class Model(torch.nn.Module):
  def __init__(self, backbone, model_config, freeze_backbone = False):
    super().__init__()
    # freeze parameter backbone jika perlu
    for param in backbone.parameters():
      _is_requires_grad = not freeze_backbone
      param.requires_grad = _is_requires_grad
    self.config = model_config
    self.backbone = backbone
    self.fc1 = torch.nn.Linear(self.config.hidden_size, COMBINED_TOKENS_SIZE)
    self.fc2 = torch.nn.Linear(COMBINED_TOKENS_SIZE, 7)
    self.activation = torch.nn.GELU()

  def forward(self, input_ids, attention_mask):
    # 1st forward pass
    output1 = self.backbone(input_ids, attention_mask)[1] # run through backbone then take the [CLS] token
    logits1 = self.fc2(self.activation(self.fc1(output1))) # run the [CLS] token through fc1, activation, and then fc2

    # 2nd forward pass
    output2 = self.backbone(input_ids, attention_mask)[1] # run through backbone then take the [CLS] token
    logits2 = self.fc2(self.activation(self.fc1(output2))) # run the [CLS] token through fc1, activation, and then fc2

    return logits1, logits2

try:
    a = 2
    b = 3
    assert(a==b)
except:
    print(a,b)

import pickle

def handle_checkpoint(eval_items, train_loss_sum_history, train_loss_history):
    with open("./eval_items.pickle", "wb") as f:
        pickle.dump(eval_items, f)

    with open("./train_loss_sum_history.pickle", "wb") as f:
        pickle.dump(train_loss_sum_history, f)

    with open("./train_loss_history.pickle", "wb") as f:
        pickle.dump(train_loss_history, f)

import requests, time

# Replace 'YOUR_BOT_TOKEN' with your bot's API token
TOKEN = '6717520904:AAGnyoWW2Ry5jmakqsfRfyrU4-Z7lLS_wJg'
BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"
CHAT_ID = "918740479"
SENDER = "COLAB experiment baseline duplicate tonyX"

def send_message(chat_id, text):
    try:
        if '```' not in text: text = f'```{SENDER.replace(" ",  "")}_undef!\n{text}```'
        url = BASE_URL + "sendMessage"
        params = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        response = requests.post(url, json=params)
        if response.status_code == 200:
            print("Message sent successfully!")
        else:
            print(f"Failed to send message. Status code: {response.status_code}")
            print(response.text)
    except:
        print("[!] failed sending message")


def send_document(chat_id, document_path):
    try:
        url = BASE_URL + "sendDocument"
        files = {'document': open(document_path, 'rb')}
        params = {'chat_id': chat_id}
        response = requests.post(url, params=params, files=files)
        if response.status_code == 200:
            print("Document sent successfully!")
        else:
            print(f"Failed to send document. Status code: {response.status_code}")
            print(response.text)
    except:
        error_message = f'[!] failed sending {document_path}'
        print(error_message)
        send_message(CHAT_ID, f'```{SENDER.replace(" ",  "")}_ERROR\nerror_message```')

def handle_telegram_report_bot(epoch, file_paths):
    global CHAT_ID, SENDER
    message = f'**`[Epoch #{epoch+1}]`** \nfrom **`[{SENDER}]`** \nis done at **`[{str(time.localtime().tm_hour+7).zfill(2)}:{str(time.localtime().tm_min).zfill(2)}]`**.'
    if epoch == -1: message = f'```{SENDER.replace(" ",  "")}_info\n[{SENDER}] INITIALIZING TRAINING...```'
    send_message(CHAT_ID, message)
    for file_path in file_paths:
        send_document(CHAT_ID, file_path)

# test file sending:
print("TEST TELEGRAM BOT MESSAGE")
handle_telegram_report_bot(-1, [])
print("...done")
"""## TRAINING"""

# TRAINING
from tqdm import tqdm
import numpy as np
import time
from torch.nn.parallel import DataParallel

BATCH_SIZE = 10
EPOCH = 10
LEARNING_RATE = 5e-6
WEIGHT_DECAY = 1e-4
WARMUP_RATE = 0.1

RDROP_WEIGHT = 0.1
FORWARD_WEIGHT = (1-RDROP_WEIGHT)/2
GRADIENT_ACC = 8

OVERALL_WEIGHT = 0.75
DIMS_WEIGHT = [OVERALL_WEIGHT if i == 4 else (1-OVERALL_WEIGHT)/6 for i in range(7)]

# keyword args dari tokenizer
kwargs = {
    "padding" : 'max_length',
    "truncation" : True,
    "max_length" : COMBINED_TOKENS_SIZE,
    "add_special_tokens": True,
    "return_tensors" : "pt"
}

def calculate_weighted_loss(y_pred, y, criterion):
  global DIMS_WEIGHT, BATCH_SIZE
  loss = 0.0
  if y.shape[0] != BATCH_SIZE or y_pred.shape[0] != BATCH_SIZE:
    print(y.shape, y_pred.shape, y.shape[0], y_pred.shape[0])
  for i in range(7):
    try:
      y_pred_i, y_i = y_pred[:, i], y[:, i]
    except:
      try:
        y_pred_i, y_i = y_pred[i], y[i]
      except:
        return loss
    loss += criterion(y_pred_i, y_i) * DIMS_WEIGHT[i]
  return loss

def predict(model, data_loader):
  global device
  print("\tinside predict")
  model.eval()
  print("\tmodel set to eval")
  test_pred, test_true = [], []
  with torch.no_grad():
    print("\tinside torch.no_grad()")
    for idx, (doc1doc2, tensor_labels) in tqdm(enumerate(data_loader), total=len(data_loader), desc="PREDICT"):
      inputs = tokenizer(doc1doc2, **kwargs).to(device)
      y_pred = model(**inputs)
      y_pred = torch.squeeze(torch.add(torch.mul(y_pred[0], 0.5), torch.mul(y_pred[1], 0.5))).detach().cpu().numpy().tolist()
      y = tensor_labels.to(device)
      y = y.squeeze().cpu().numpy().tolist()

      if not type(y[0]) == list: y = [y]
      if not type(y_pred[0]) == list: y_pred = [y_pred]

      test_true.extend([x[4] for x in y])
      test_pred.extend([x[4] for x in y_pred])
      # try:
      # except:
      #   print(idx)
      #   print(y)
      #   print(y_pred)
    return test_true, test_pred

# buat data_loader
train_data_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
eval_data_loader = DataLoader(eval_ds, batch_size=BATCH_SIZE, shuffle=True)

model = Model(backbone, model_config)
for param in model.parameters():
    param.requires_grad = True

total_steps = len(train_data_loader) * EPOCH
criterion = torch.nn.MSELoss()
optimizer = AdamW(params=model.parameters(),
                  lr=LEARNING_RATE,
                  weight_decay=WEIGHT_DECAY)

schedule = get_cosine_schedule_with_warmup(optimizer=optimizer,
                                           num_warmup_steps=WARMUP_RATE*total_steps,
                                           num_training_steps=total_steps)

# untuk gpu training
# device = torch.device("cpu")
# device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
device = torch.device("cuda:0")
if torch.cuda.is_available(): torch.cuda.empty_cache() # Clear all CUDA memory
# Check if multiple GPUs are available
if torch.cuda.device_count() > 1:
    print("Let's use", torch.cuda.device_count(), "GPUs!")
    model = DataParallel(model)
model.to(device)
model.train()

train_loss_history = []
train_loss_sum_history = []
# eval_loss_sum_history = []
eval_items = []
pearson_cc_history = []

bar = tqdm(total=EPOCH * len(train_data_loader), desc="Train")

best_pearson = 0.0
try: send_message(CHAT_ID, f'```{SENDER.replace(" ",  "")}_info\n[TRAINING STARTED]\n{MODEL_NAME=}\n{COMBINED_TOKENS_SIZE=}\n{BATCH_SIZE=}\n{EPOCH=}\n{LEARNING_RATE=}```')
except: pass
try:
  for e in range(EPOCH):
    try: send_message(CHAT_ID, f'```{SENDER.replace(" ",  "")}_info\n> epoch {e+1}```')
    except: pass
    start_time = time.time()
    train_loss_sum = 0.0

    for doc1doc2, tensor_labels in train_data_loader:
      # ngosongin gradien yang menumpuk di backendnya torch
      optimizer.zero_grad()

      # tokenize dari string, kemudian dipindah ke device gpu jika pake
      inputs = tokenizer(doc1doc2, **kwargs).to(device)
      y = tensor_labels.to(device)

      y_pred1, y_pred2 = model(**inputs)
      y_pred1, y_pred2, y = torch.squeeze(y_pred1), torch.squeeze(y_pred2), torch.squeeze(y)


      loss1 = calculate_weighted_loss(y_pred1, y, criterion) * FORWARD_WEIGHT
      loss2 = calculate_weighted_loss(y_pred2, y, criterion) * FORWARD_WEIGHT
      loss_r = calculate_weighted_loss(y_pred1, y_pred2, criterion) * RDROP_WEIGHT
      loss = (loss1 + loss2 + loss_r) / GRADIENT_ACC

      optimizer.zero_grad()
      loss.backward()
      optimizer.step()
      schedule.step()
      train_loss_sum += loss.item()

      train_loss_history.append(loss)
      bar.update()

    train_loss_sum_history.append(train_loss_sum)

    print("Start evaluating!")
    # TODO: update eval_data_loader into validation_data_loader!
    # WARNING: this is just for testing purpose. you should validate using different dataset from eval_dataset
    #
    # dev_true, dev_pred = predict(model, valid_loader)
    dev_true, dev_pred = predict(model, eval_data_loader)
    cur_pearson = np.corrcoef(dev_true, dev_pred)[0][1]
    eval_info = {
      "dev_true": dev_true,
      "dev_pred": dev_pred,
      "pearson_cc": cur_pearson,
    }
    eval_items.append(eval_info)
  #   eval_loss_sum = 0.0
  #   for i in range(len(dev_true)):
  #     y_pred = dev_pred[i]
  #     y_true = dev_true[i]
  #     eval_loss1 = calculate_weighted_loss(y_pred, dey_true, criterion) * FORWARD_WEIGHT
  #     eval_loss2 = calculate_weighted_loss(y_pred, y_true, criterion) * FORWARD_WEIGHT
  #     eval_loss_r = calculate_weighted_loss(y_pred, y_pred, criterion) * RDROP_WEIGHT
  #     eval_loss = (eval_loss1 + eval_loss2 + eval_loss_r) / GRADIENT_ACC
  #     eval_loss_sum += eval_loss
  #   eval_loss_sum_history.append(eval_loss_sum)

    print("Current dev pearson is {:.4f}, best pearson is {:.4f}".format(cur_pearson, best_pearson))
    if cur_pearson > best_pearson:
      best_pearson = cur_pearson
      print("\tSAVING MODEL...")
      torch.save(model.state_dict(), MODEL_PATH)
      # Copy the file from Colab to Google Drive
      # try: shutil.copyfile(MODEL_PATH, DRIVE_MODEL_PATH)
      # except Exception as e: send_message(CHAT_ID, f'ERROR\ncannot save to google drive:\n{e}')
      print("\tDONE")
    print("Time costed : {}s".format(round(time.time() - start_time, 3)))
    print(f'LOSS: {train_loss_sum=} | \n')
    print("SAVING CHECKPOINT...")
    handle_checkpoint(eval_items, train_loss_sum_history, train_loss_history)
    print("DONE")
    print("SENDING REPORT THROUGH TELEGRAM BOT...")
    file_paths = ["./eval_items.pickle",
                  "./train_loss_sum_history.pickle",
                  "./train_loss_history.pickle"]
    handle_telegram_report_bot(e, file_paths)
    try: send_message(CHAT_ID, f'{cur_pearson=}\n{best_pearson=}\n{train_loss_sum=}\n```\n----------```')
    except: pass
except Exception as e:
  try:
    training_error_message = f'[ERROR]\nTraining from {SENDER} is unexpectedly stopped at [{str(time.localtime().tm_hour+7).zfill(2)}:{str(time.localtime().tm_min).zfill(2)}].\n{e=}'
    print(training_error_message)
  except: pass
  try:
    send_message(CHAT_ID, f'```{SENDER.replace(" ",  "")}_ERROR\n{training_error_message}```')
  except: pass

# print(f'{eval_items=}')
# print(f'{train_loss_sum_history=}')
# print(f'{train_loss_history=}')
import os
try:
    send_message(CHAT_ID, f'```{SENDER.replace(" ",  "")}_info\nExecution finished, shutting down {SENDER}\'s PC.```')
#     os.system("shutdown now -h")
    send_message(CHAT_ID, f'```{SENDER.replace(" ",  "")}_finished\n...done```')
except: pass

# from IPython.display import FileLink
# !zip -r saved_models.zip ./saved_models

# FileLink(r'eval_items.pickle')
# FileLink(r'train_loss_sum_history.pickle')
# FileLink(r'train_loss_history.pickle')
