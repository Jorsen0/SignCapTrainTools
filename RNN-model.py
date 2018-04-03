# coding:utf-8
import os
import pickle
import random
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.data as Data
from torch.autograd import Variable

# 由于softmax输出的是十四个概率值 于是取最大的那个就是最可能正确的答案
# 取最大值 并且转换为int
def getMaxIndex(tensor):
    # print('置信度')
    # print(tensor[60].data.float())
    tensor = torch.max(tensor, dim=1)[1]
    # 对矩阵延一个固定方向取最大值
    return torch.squeeze(tensor).data.int()

CUDA_AVAILABLE = torch.cuda.is_available()
print('cuda_status: %s' % str(CUDA_AVAILABLE))

DATA_DIR_PATH = os.getcwd() + '\\data'
BATCH_SIZE = 128
EPOCH = 1000
NNet_SIZE = 30
NNet_LEVEL = 3
NNet_output_size = 24
CLASS_COUNT = 24
LEARNING_RATE = 0.0005


# load data
f = open(DATA_DIR_PATH + '\\data_set', 'r+b')
raw_data = pickle.load(f)
f.close()

# 检查rawData中 feedback数据集是否存在
try:
    raw_data = raw_data[1].extend(raw_data[2])
except IndexError:
    raw_data = raw_data[1]
# train_data => (batch_amount, data_set_emg)

random.shuffle(raw_data)

# process data
data_input, data_label = [], []
cnt = 0
for (each_label, each_data) in raw_data:
    if len(each_data) == 10:
        data_input.append(each_data)
        data_label.append(each_label - 1)
    else:
        print("len error")
print('data_len: %s' % len(data_input))

data_input = torch.from_numpy(np.array(data_input)).float()
data_label = torch.from_numpy(np.array(data_label))


# split and batch with data loader
# 0~500 test
test_input_init = data_input[:500]
test_label = data_label[:500]

# 500~n train
training_input = data_input[101:]
training_label = data_label[101:]
training_set = Data.TensorDataset(data_tensor=training_input,
                                  target_tensor=training_label)
loader = Data.DataLoader(
    dataset=training_set,
    batch_size=BATCH_SIZE,  # should be tuned when data become bigger
    shuffle=True
)

class LSTM(nn.Module):
    def __init__(self):
        super(LSTM, self).__init__()
        self.lstm = nn.LSTM(
            input_size=44,  # feature's number
            # 2*(3+3+3*4) +(8 + 8 +4*8)
            hidden_size=NNet_SIZE,  # hidden size of rnn layers
            num_layers=NNet_LEVEL,  # the number of rnn layers
            # hidden_size=20,  # hidden size of rnn layers
            # num_layers=2,  # the number of rnn layers
            batch_first=True,
            dropout=0.50)
        # dropout :
        # 在训练时，每次随机（如 50% 概率）忽略隐层的某些节点；
        # 这样，我们相当于随机从 2^H 个模型中采样选择模型；同时，由于每个网络只见过一个训练数据
        # 使得模型保存一定的随机性 避免过拟合严重
        self.out = nn.Linear(NNet_SIZE, NNet_output_size)
        self.out2 = nn.Linear(NNet_output_size, CLASS_COUNT)
        # use soft max classifier.
        # 在输出层中间加了层softmax 用于分类
        # softmax将会输出这十四个结果每个可能是正确的概率
        # self.out = nn.Linear(20, 12)
        # self.out2 = nn.Linear(12, 14)

    def forward(self, x):
        lstm_out, (h_n, h_c) = self.lstm(x, None)
        out = F.relu(lstm_out)
        out = self.out(out[:, -1, :])
        out = F.relu(out)
        # return out

        out2 = self.out2(out)
        out2 = F.softmax(out2)
        return out2


# define loss function and optimizer
model = LSTM()

# encoder = AutoEncoder()
# encoder.load_state_dict(torch.load('autoencoder_model03-22,21-15.pkl'))
# encoder.eval()

model.cuda()
# 转换为GPU对象

model.train()
# 转换为训练模式

loss_func = nn.CrossEntropyLoss()
optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=0.0000002)
# learning rate can be tuned for better performance

start_time_raw = time.time()
start_time = time.strftime('%H:%M:%S', time.localtime(start_time_raw))
print('start_at: %s' % start_time)

# start training
# epoch: 用所有训练数据跑一遍称为一次epoch
for epoch in range(0, EPOCH):

    for batch_x, batch_y in loader:
        batch_x = Variable(batch_x).cuda()
        batch_y = Variable(batch_y).cuda()
        batch_out = model(batch_x)
        batch_out = torch.squeeze(batch_out)    
        loss = loss_func(batch_out, batch_y)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    if epoch % 20 == 0:
        model.eval()
        # 转换为求值模式
        test_input = Variable(test_input_init).cuda()  # 转换在gpu内跑识别
        # 转换为可读取的输入 Variable
        # 如下进行nn的正向使用 分类
        test_output = model(test_input).cpu()  # 从gpu中取回cpu算准确度
        # 需要从gpu的显存中取回内存进行计算正误率
        test_output = getMaxIndex(test_output)
        # softmax是14个概率的输出
        # test数据是连续的100个输入 于是输出也是一个 100 * 14 的矩阵
        test_output = test_output.numpy()
        testLabel_ = test_label.numpy()
        right = 0
        error = 0
        for i in range(len(testLabel_)):
            if test_output[i] == testLabel_[i]:
                right += 1
            else:
                error += 1
        result = right / (right + error)
        print("epoch: %s\naccuracy: %s\nloss: %s" % (epoch, result, loss.data.float()))

end_time_raw = time.time()
end_time = time.strftime('%H:%M:%S', time.localtime(end_time_raw))
print('end_at: %s' % end_time)

cost_time = end_time_raw - start_time_raw
cost_time = time.strftime('%H:%M:%S', time.gmtime(cost_time, ))
print('cost time: %s' % cost_time)

end_time = time.strftime('%m-%d,%H-%M', time.localtime(end_time_raw))
torch.save(model.state_dict(), 'model_param%s.pkl' % end_time)

file = open('models_info_%s' % end_time, 'w')
file.writelines('batch_size:%d\naccuracy:%f\nloss: %f\nNNet:%d x %d\nEpoch: %d\nNNet output size: %d\nclasses cnt %d' %
                (BATCH_SIZE, result, loss.data.float()[0], NNet_LEVEL, NNet_SIZE, EPOCH, NNet_output_size, CLASS_COUNT))
file.close()
# how to read? :
# model.load_state_dict(torch.load('model_param.pkl'))
