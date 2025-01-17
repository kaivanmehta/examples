from __future__ import print_function
import argparse
from math import log10

import time
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from model import Net
from data import get_training_set, get_test_set
from nni.algorithms.compression.v2.pytorch.pruning import L1NormPruner, FPGMPruner
from nni.compression.pytorch.speedup import ModelSpeedup
from nni.algorithms.compression.pytorch.quantization import NaiveQuantizer, QAT_Quantizer, DoReFaQuantizer, BNNQuantizer, LsqQuantizer, ObserverQuantizer


# Training settings
parser = argparse.ArgumentParser(description='PyTorch Super Res Example')
parser.add_argument('--upscale_factor', type=int, required=True, help="super resolution upscale factor")
parser.add_argument('--batchSize', type=int, default=64, help='training batch size')
parser.add_argument('--testBatchSize', type=int, default=10, help='testing batch size')
parser.add_argument('--nEpochs', type=int, default=2, help='number of epochs to train for')
parser.add_argument('--lr', type=float, default=0.01, help='Learning Rate. Default=0.01')
parser.add_argument('--cuda', action='store_true', help='use cuda?')
parser.add_argument('--mps', action='store_true', default=False, help='enables macOS GPU training')
parser.add_argument('--threads', type=int, default=4, help='number of threads for data loader to use')
parser.add_argument('--seed', type=int, default=123, help='random seed to use. Default=123')
opt = parser.parse_args()

print(opt)

if opt.cuda and not torch.cuda.is_available():
    raise Exception("No GPU found, please run without --cuda")
# if not opt.mps and torch.backends.mps.is_available():
#     raise Exception("Found mps device, please run with --mps to enable macOS GPU")

torch.manual_seed(opt.seed)
use_mps = False # opt.mps and torch.backends.mps.is_available()

if opt.cuda:
    device = torch.device("cuda")
elif use_mps:
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print('===> Loading datasets')
train_set = get_training_set(opt.upscale_factor)
test_set = get_test_set(opt.upscale_factor)
training_data_loader = DataLoader(dataset=train_set, num_workers=opt.threads, batch_size=opt.batchSize, shuffle=True)
testing_data_loader = DataLoader(dataset=test_set, num_workers=opt.threads, batch_size=opt.testBatchSize, shuffle=False)

print('===> Building model')
model = Net(upscale_factor=opt.upscale_factor).to(device)
print(model)

criterion = nn.MSELoss()
optimizer = optim.Adam(model.parameters(), lr=opt.lr)

def train(epoch):
    epoch_loss = 0
    for iteration, batch in enumerate(training_data_loader, 1):
        input, target = batch[0].to(device), batch[1].to(device)

        optimizer.zero_grad()
        loss = criterion(model(input), target)
        epoch_loss += loss.item()
        loss.backward()
        optimizer.step()

        print("===> Epoch[{}]({}/{}): Loss: {:.4f}".format(epoch, iteration, len(training_data_loader), loss.item()))

    print("===> Epoch {} Complete: Avg. Loss: {:.4f}".format(epoch, epoch_loss / len(training_data_loader)))


def test():
    avg_psnr = 0
    with torch.no_grad():
        for batch in testing_data_loader:
            input, target = batch[0].to(device), batch[1].to(device)
            prediction = model(input)
            mse = criterion(prediction, target)
            psnr = 10 * log10(1 / mse.item())
            avg_psnr += psnr
    print("===> Avg. PSNR: {:.4f} dB".format(avg_psnr / len(testing_data_loader)))


def checkpoint(epoch):
    model_out_path = "model_epoch_{}.pth".format(epoch)
    torch.save(model, model_out_path)
    print("Checkpoint saved to {}".format(model_out_path))


start = time.time()
for epoch in range(1, opt.nEpochs + 1):
    train(epoch)
    test()
stop = time.time()
print("before quantization: entire training took: ", (stop - start)/60, "minutes!")

#     checkpoint(epoch)
 

# config_list = [{
#     'sparsity': 0.5,
#     'op_types': ['Conv2d']
# }]

config_list = [{
    'sparsity': 0.5,
    'op_types': ['Conv2d']
    }
   ]

# pruner = L1NormPruner(model, config_list)
# _, masks = pruner.compress()
# print("enclosed model")
# print(model)
# # show the masks sparsity
# print("------------- sparsity ----------------")
# for name, mask in masks.items():
#     print(name, ' sparsity : ', '{:.2}'.format(mask['weight'].sum() / mask['weight'].numel()))

# pruner._unwrap_model()
# ModelSpeedup(model, torch.rand(3, 1, 28, 28).to(device), masks).speedup_model()
print(model)
config_list = [{
      'quant_types': ['weight', 'input'],
      'quant_bits': {'weight': 16, 'input': 16}, 
      'op_types': ['Conv2d'],
    }]
QAT_Quantizer(model, config_list, optimizer, dummy_input = torch.randn(10, 1, 64, 64).to(device)).compress()

print(model)
    
start = time.time()
for epoch in range(1, opt.nEpochs + 1):
    train(epoch)
    test()
stop = time.time()
print("after quantization: entire training took: ", (stop - start)/60, "minutes!")

# torch.onnx.export(
#                 model,
#                 torch.randn(10,1,64,64).to(device),  
#                 "./onnx/super_resolution.onnx", 
#                 do_constant_folding=True,
#                 input_names=['input'],  # the model's input names (an arbitrary string)
#                 output_names=['output'],  # the model's output names (an arbitrary string)
#                 opset_version=11  # XGen supports 11 or 9
#             )

# pruner = L1NormPruner(model, config_list)
# _, masks = pruner.compress()

# print(model)

# # show the masks sparsity
# for name, mask in masks.items():
#     print(name, ' sparsity : ', '{:.2}'.format(mask['weight'].sum() / mask['weight'].numel()))
   
# # pruner._unwrap_model()
# # ModelSpeedup(model, torch.rand(3, 1, 28, 28).to(device), masks).speedup_model()
