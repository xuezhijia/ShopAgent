/*
 Navicat Premium Data Transfer

 Source Server         : XueZhiJia
 Source Server Type    : MySQL
 Source Server Version : 80016
 Source Host           : localhost:3306
 Source Schema         : ai_db

 Target Server Type    : MySQL
 Target Server Version : 80016
 File Encoding         : 65001

 Date: 10/06/2026 12:30:27
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for order
-- ----------------------------
DROP TABLE IF EXISTS `order`;
CREATE TABLE `order`  (
  `id` int(11) NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `number` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '订单号',
  `status` int(11) NOT NULL COMMENT '订单状态 0：已付款 1：已发货 2：已送达',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 4 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_general_ci ROW_FORMAT = Dynamic;

-- ----------------------------
-- Records of order
-- ----------------------------
INSERT INTO `order` VALUES (1, 'ORD0123456789', 0);
INSERT INTO `order` VALUES (2, 'ORD1234567896', 1);
INSERT INTO `order` VALUES (3, 'ORD1234567895', 2);

SET FOREIGN_KEY_CHECKS = 1;
