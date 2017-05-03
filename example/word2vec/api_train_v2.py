import gzip
import math

import paddle.v2 as paddle
import paddle_job.job as job
from job import Paddlejob, dist_train,CephVolume
import os
embsize = 32
hiddensize = 256
N = 5


def wordemb(inlayer):
    wordemb = paddle.layer.embedding(
        input=inlayer,
        size=embsize,
        param_attr=paddle.attr.Param(
            name="_proj",
            initial_std=0.001,
            learning_rate=1,
            l2_rate=0,
            sparse_update=True))
    return wordemb


def fetch_trainer_id():
    return int(os.getenv("TRAINER_ID", 0))


def fetch_pserver_ips():
    return os.getenv("PSERVER_IPS", "")


def main():
    # for local training
    cluster_train = True

    if not cluster_train:
        paddle.init(use_gpu=False, trainer_count=1)
    else:
        paddle.init(
            use_gpu=False,
            trainer_count=1,
            port=7164,
            ports_num=1,
            ports_num_for_sparse=1,
            num_gradient_servers=1,
            trainer_id=fetch_trainer_id(),
            pservers=fetch_pserver_ips())
    word_dict = paddle.dataset.imikolov.build_dict()
    dict_size = len(word_dict)
    firstword = paddle.layer.data(
        name="firstw", type=paddle.data_type.integer_value(dict_size))
    secondword = paddle.layer.data(
        name="secondw", type=paddle.data_type.integer_value(dict_size))
    thirdword = paddle.layer.data(
        name="thirdw", type=paddle.data_type.integer_value(dict_size))
    fourthword = paddle.layer.data(
        name="fourthw", type=paddle.data_type.integer_value(dict_size))
    nextword = paddle.layer.data(
        name="fifthw", type=paddle.data_type.integer_value(dict_size))

    Efirst = wordemb(firstword)
    Esecond = wordemb(secondword)
    Ethird = wordemb(thirdword)
    Efourth = wordemb(fourthword)

    contextemb = paddle.layer.concat(input=[Efirst, Esecond, Ethird, Efourth])
    hidden1 = paddle.layer.fc(input=contextemb,
                              size=hiddensize,
                              act=paddle.activation.Sigmoid(),
                              layer_attr=paddle.attr.Extra(drop_rate=0.5),
                              bias_attr=paddle.attr.Param(learning_rate=2),
                              param_attr=paddle.attr.Param(
                                  initial_std=1. / math.sqrt(embsize * 8),
                                  learning_rate=1))
    predictword = paddle.layer.fc(input=hidden1,
                                  size=dict_size,
                                  bias_attr=paddle.attr.Param(learning_rate=2),
                                  act=paddle.activation.Softmax())

    def event_handler(event):
        if isinstance(event, paddle.event.EndIteration):
            if event.batch_id % 100 == 0:
                with gzip.open("batch-" + str(event.batch_id) + ".tar.gz",
                               'w') as f:
                    trainer.save_parameter_to_tar(f)
                result = trainer.test(
                    paddle.batch(
                        paddle.dataset.imikolov.test(word_dict, N), 32))
                print "Pass %d, Batch %d, Cost %f, %s, Testing metrics %s" % (
                    event.pass_id, event.batch_id, event.cost, event.metrics,
                    result.metrics)

    cost = paddle.layer.classification_cost(input=predictword, label=nextword)

    parameters = paddle.parameters.create(cost)
    adagrad = paddle.optimizer.AdaGrad(
        learning_rate=3e-3,
        regularization=paddle.optimizer.L2Regularization(8e-4))
    trainer = paddle.trainer.SGD(cost,
                                 parameters,
                                 adagrad,
                                 is_local=not cluster_train)
    job.dist_train(
        trainer=trainer,
        reader=paddle.batch(paddle.dataset.imikolov.train(word_dict, N), 32),
        num_passes=30,
        event_handler=event_handler,
        paddle_job=PaddleJob(
            trainers=3,
            pservers=3,
            base_image="yancey1989/paddle-cloud",
            glusterfs_volume="gfs_vol",
            input="/yanxu05",
            output="/yanxu05",
            job_name="paddle-cloud",
            namespace="yanxu",
            use_gpu=False,
            trainer_package_path="/yanxu05/word2vec",
            entry_point="python api_train_v2.py",
            ceph_volume=CephVolume()),
    )


if __name__ == '__main__':
    main()