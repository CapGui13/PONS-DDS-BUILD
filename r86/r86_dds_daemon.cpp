#include <algorithm>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include "dll.h"

static void writeCanonical(std::ostream& out, const ddTableResults& t) {
  const int strains[5] = {4, 0, 1, 2, 3}; // NT,S,H,D,C
  const int seats[4] = {0, 2, 1, 3};       // N,S,E,W
  bool first = true;
  for (int si = 0; si < 5; ++si) {
    for (int hi = 0; hi < 4; ++hi) {
      if (!first) out << ',';
      first = false;
      out << t.resTable[strains[si]][seats[hi]];
    }
  }
}

int main(int argc, char** argv) {
  if (argc != 3) {
    std::cerr << "usage: r86_dds_daemon <threads> <batchSize>\n";
    return 2;
  }
  const int threads = std::stoi(argv[1]);
  const int batchSize = std::stoi(argv[2]);
  if (threads < 1 || threads > 2 || batchSize < 1 || batchSize > 40) return 3;
  SetMaxThreads(threads);

  std::string line;
  while (std::getline(std::cin, line)) {
    if (line.empty()) continue;
    if (line == "PING") {
      std::cout << "PONG\n" << std::flush;
      continue;
    }
    if (line == "QUIT") break;

    int n = 0;
    try { n = std::stoi(line); } catch (...) {
      std::cout << "ERR\tbad-count\n" << std::flush;
      continue;
    }
    if (n < 1 || n > 40) {
      std::cout << "ERR\tcount-out-of-range\n" << std::flush;
      continue;
    }

    std::vector<std::string> pbns;
    pbns.reserve(static_cast<size_t>(n));
    bool input_ok = true;
    for (int i = 0; i < n; ++i) {
      std::string pbn;
      if (!std::getline(std::cin, pbn)) { input_ok = false; break; }
      if (pbn.empty() || pbn.size() >= sizeof(ddTableDealPBN{}.cards)) input_ok = false;
      pbns.push_back(std::move(pbn));
    }
    if (!input_ok || static_cast<int>(pbns.size()) != n) {
      std::cout << "ERR\tbad-pbn-input\n" << std::flush;
      if (!std::cin) break;
      continue;
    }

    std::vector<ddTableResults> all(static_cast<size_t>(n));
    int filter[DDS_STRAINS] = {0,0,0,0,0};
    bool ok = true;
    std::string err;

    for (int pos = 0; pos < n; pos += batchSize) {
      const int k = std::min(batchSize, n - pos);
      ddTableDealsPBN deals{};
      ddTablesRes results{};
      allParResults par{};
      deals.noOfTables = k;
      for (int i = 0; i < k; ++i) {
        std::strncpy(deals.deals[i].cards, pbns[static_cast<size_t>(pos + i)].c_str(), sizeof(deals.deals[i].cards) - 1);
      }
      const int rc = CalcAllTablesPBN(&deals, 0, filter, &results, &par);
      if (rc != RETURN_NO_FAULT) {
        char msg[80]{};
        ErrorMessage(rc, msg);
        ok = false;
        err = msg;
        break;
      }
      for (int i = 0; i < k; ++i) all[static_cast<size_t>(pos + i)] = results.results[i];
    }

    if (!ok) {
      std::cout << "ERR\t" << err << "\n" << std::flush;
      continue;
    }
    std::cout << "OK\t" << n << "\n";
    for (const auto& table : all) {
      writeCanonical(std::cout, table);
      std::cout << '\n';
    }
    std::cout << std::flush;
  }

  FreeMemory();
  return 0;
}
