#include <algorithm>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include "dll.h"

static std::vector<std::string> splitTabs(const std::string& line){
  std::vector<std::string> z; std::string x; std::stringstream ss(line);
  while(std::getline(ss,x,'\t')) z.push_back(x); return z;
}
static void writeCanonical(std::ostream& out,const ddTableResults& t){
  const int strains[5]={4,0,1,2,3};
  const int seats[4]={0,2,1,3};
  bool first=true;
  for(int si=0;si<5;++si) for(int hi=0;hi<4;++hi){
    if(!first) out << ','; first=false;
    out << t.resTable[strains[si]][seats[hi]];
  }
}
struct Row { std::string a,b,c,pbn; };

int main(int argc,char** argv){
  if(argc!=7){
    std::cerr << "usage: dds_batch_bench <seq|batch> <threads> <batchSize> <input.tsv> <output.tsv> <meta.txt>\n";
    return 2;
  }
  const std::string mode=argv[1];
  const int threads=std::stoi(argv[2]);
  const int batchSize=std::stoi(argv[3]);
  if((mode!="seq" && mode!="batch") || threads<1 || threads>2 || batchSize<1 || batchSize>40) return 3;
  SetMaxThreads(threads);
  std::ifstream in(argv[4]); std::ofstream out(argv[5]); std::ofstream meta(argv[6]);
  if(!in||!out||!meta) return 4;
  std::vector<Row> rows; std::string line;
  while(std::getline(in,line)){
    if(line.empty()) continue;
    const auto z=splitTabs(line);
    if(z.size()!=4){ std::cerr << "bad input row fields=" << z.size() << "\n"; return 5; }
    rows.push_back({z[0],z[1],z[2],z[3]});
  }
  long long calls=0;
  if(mode=="seq"){
    for(const auto& r:rows){
      ddTableDealPBN d{}; std::strncpy(d.cards,r.pbn.c_str(),sizeof(d.cards)-1);
      ddTableResults t{}; const int rc=CalcDDtablePBN(d,&t); ++calls;
      if(rc!=RETURN_NO_FAULT){ char msg[80]{}; ErrorMessage(rc,msg); std::cerr << "DDS error " << msg << "\n"; return 6; }
      out << r.a << '\t' << r.b << '\t' << r.c << '\t'; writeCanonical(out,t); out << '\n';
    }
  } else {
    int filter[DDS_STRAINS]={0,0,0,0,0};
    for(size_t pos=0;pos<rows.size();pos+=static_cast<size_t>(batchSize)){
      const int n=static_cast<int>(std::min(rows.size()-pos,static_cast<size_t>(batchSize)));
      ddTableDealsPBN deals{}; ddTablesRes results{}; allParResults par{};
      deals.noOfTables=n;
      for(int i=0;i<n;++i) std::strncpy(deals.deals[i].cards,rows[pos+i].pbn.c_str(),sizeof(deals.deals[i].cards)-1);
      const int rc=CalcAllTablesPBN(&deals,0,filter,&results,&par); ++calls;
      if(rc!=RETURN_NO_FAULT){ char msg[80]{}; ErrorMessage(rc,msg); std::cerr << "DDS batch error " << msg << " n=" << n << "\n"; return 7; }
      for(int i=0;i<n;++i){ const auto& r=rows[pos+i]; out << r.a << '\t' << r.b << '\t' << r.c << '\t'; writeCanonical(out,results.results[i]); out << '\n'; }
    }
  }
  meta << "mode=" << mode << "\nthreads=" << threads << "\nbatchSize=" << batchSize << "\nrows=" << rows.size() << "\ncalls=" << calls << "\n";
  FreeMemory(); return 0;
}
