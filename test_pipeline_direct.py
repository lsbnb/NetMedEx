#!/usr/bin/env python
"""
直接測試 NetMedEx Pipeline
測試從 diabetes.pubtator 文件構建圖形的完整流程
"""

import sys
sys.path.insert(0, '/home/cylin/NetMedEx')

from netmedex.pubtator_parser import PubTatorIO
from netmedex.graph import PubTatorGraphBuilder
from webapp.llm import llm_client

def progress_callback(current, total, status, error):
    """進度回調函數"""
    if error:
        print(f"❌ ERROR: {error}")
    else:
        percentage = (current / total * 100) if total > 0 else 0
        print(f"📊 進度: {current}/{total} ({percentage:.1f}%) - {status}")

def main():
    print("=" * 60)
    print("NetMedEx Pipeline 測試腳本")
    print("=" * 60)
    
    # 步驟 1: 讀取 PubTator 文件
    print("\n步驟 1: 讀取 diabetes.pubtator 文件...")
    pubtator_file = "/home/cylin/NetMedEx/examples/diabetes.pubtator"
    
    try:
        collection = PubTatorIO.parse(pubtator_file)
        print(f"✅ 成功讀取 {len(collection.articles)} 篇文章")
        print(f"   文章 PMIDs: {[a.pmid for a in collection.articles[:5]]}... (showing first 5)")
    except Exception as e:
        print(f"❌ 讀取文件失敗: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 步驟 2: 檢查 LLM 配置
    print("\n步驟 2: 檢查 LLM 配置...")
    if llm_client.client:
        print(f"✅ LLM Client 已初始化")
        print(f"   Model: {llm_client.model}")
        print(f"   Base URL: {llm_client.base_url}")
    else:
        print("⚠️  LLM Client 未初始化 (Semantic Analysis 將無法使用)")
    
    # 步驟 3: 測試不同的 edge 構建方法
    edge_methods = ["co-occurrence", "relation"]  # 暫時跳過 semantic
    
    for edge_method in edge_methods:
        print(f"\n{'=' * 60}")
        print(f"步驟 3.{edge_methods.index(edge_method) + 1}: 測試 Edge Method = '{edge_method}'")
        print(f"{'=' * 60}")
        
        try:
            # 創建 graph builder
            graph_builder = PubTatorGraphBuilder(
                node_type="chemical+gene+disease",
                edge_method=edge_method,
                progress_callback=progress_callback
            )
            
            # 添加文章
            print(f"   添加文章到 graph builder...")
            for i, article in enumerate(collection.articles[:5], 1):  # 只測試前 5 篇
                print(f"   [{i}/5] Processing PMID {article.pmid}...")
                graph_builder.add_article(article)
            
            # 構建圖形
            print(f"\n   構建網路圖形...")
            G = graph_builder.build(
                weighting_method="freq",
                edge_weight_cutoff=0,
                max_edges=0
            )
            
            # 輸出結果
            print(f"\n✅ 圖形構建成功！")
            print(f"   節點數: {G.number_of_nodes()}")
            print(f"   邊數: {G.number_of_edges()}")
            
            # 顯示一些樣本節點
            if G.number_of_nodes() > 0:
                sample_nodes = list(G.nodes(data=True))[:3]
                print(f"\n   樣本節點:")
                for node_id, data in sample_nodes:
                    print(f"     - {data.get('name', node_id)} (type: {data.get('type', 'unknown')})")
            
            # 顯示一些樣本邊
            if G.number_of_edges() > 0:
                sample_edges = list(G.edges(data=True))[:3]
                print(f"\n   樣本邊:")
                for u, v, data in sample_edges:
                    u_name = G.nodes[u].get('name', u)
                    v_name = G.nodes[v].get('name', v)
                    weight = data.get('weight', 'N/A')
                    print(f"     - {u_name} <-> {v_name} (weight: {weight})")
            
        except Exception as e:
            print(f"❌ 圖形構建失敗: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("測試完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
